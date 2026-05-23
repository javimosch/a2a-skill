#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Async Client Library — Asyncio-based API for high-performance a2a messaging.

Provides async/await interface for concurrent agent patterns.
"""

import aiosqlite
import asyncio
import math
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable


def _validate_project_name(name: str) -> None:
    """Reject project names that could cause path traversal or directory escape."""
    if not name or not name.strip():
        raise ValueError("project name must not be empty")
    if "/" in name or "\\" in name or name[0] == ".":
        raise ValueError(f"invalid project name {name!r} — must not contain path separators or start with '.'")


class A2AClientAsync:
    """Async client for a2a peer-to-peer messaging."""

    def __init__(self, project: str, agent_id: str):
        """Initialize async a2a client.

        Args:
            project: Project name
            agent_id: This agent's ID

        Raises:
            ValueError: If project or agent_id is empty
        """
        if not project or not project.strip():
            raise ValueError("project must not be empty")
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        _validate_project_name(project)
        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"
        self._conn: Optional[aiosqlite.Connection] = None

    async def _cleanup_expired(self, conn: aiosqlite.Connection) -> int:
        """Delete messages past their TTL. Return count deleted."""
        ts = time.time()
        cursor = await conn.execute(
            "DELETE FROM messages WHERE ttl_seconds IS NOT NULL "
            "AND created_at + ttl_seconds < ?",
            (ts,)
        )
        return cursor.rowcount

    async def _connect(self) -> aiosqlite.Connection:
        """Get database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self.db_path), timeout=10.0)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    async def close(self):
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def send(
        self,
        to: str,
        message: str,
        ttl_seconds: Optional[int] = None,
        thread_id: Optional[str] = None,
    ) -> int:
        """Send a message.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            ttl_seconds: Optional time-to-live in seconds
            thread_id: Optional thread ID to group related messages

        Returns:
            Message ID

        Raises:
            ValueError: If recipient is empty or ttl_seconds is not positive
        """
        conn = await self._connect()
        if not to or not to.strip():
            raise ValueError("recipient must not be empty")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive number of seconds")
        recipient = None if to.lower() in ("all", "*", "broadcast") else to
        await conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.agent_id, recipient, message, thread_id, ttl_seconds, time.time()),
        )
        await conn.commit()
        cursor = await conn.execute("SELECT last_insert_rowid() as id")
        row = await cursor.fetchone()
        return row["id"] if row else 0

    async def register(
        self,
        role: str,
        prompt: str = "",
        cli: str = "",
        pid: int | None = None,
        upsert: bool = True,
    ) -> bool:
        """Register this agent on the bus (async).

        Args:
            role: Agent's role description
            prompt: System prompt (optional)
            cli: CLI tool name (optional)
            pid: Process ID (optional, must be > 0 if provided)
            upsert: Replace existing registration if True

        Returns:
            True on success
        """
        if pid is not None and pid <= 0:
            raise ValueError("pid must be a positive integer")
        conn = await self._connect()
        sql = (
            "INSERT OR REPLACE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            if upsert else
            "INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        now = time.time()
        await conn.execute(sql, (self.agent_id, role, prompt, cli, "active", pid, now, now))
        await conn.commit()
        return True

    async def unregister(self) -> bool:
        """Remove this agent from the bus (async).

        Returns:
            True on success
        """
        conn = await self._connect()
        await conn.execute("DELETE FROM agents WHERE id = ?", (self.agent_id,))
        await conn.commit()
        return True

    async def recv(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Max seconds to wait for messages (supports fractional)
            unread_only: Only return unread messages
            include_self: Include messages from self
            limit: Max number of messages to return

        Returns:
            List of message dicts

        Raises:
            ValueError: If wait is negative

        """
        conn = await self._connect()
        if wait < 0:
            raise ValueError("wait must be a non-negative number of seconds")
        if not math.isfinite(wait):
            raise ValueError("wait must be a finite number")
        deadline = time.time() + wait if wait > 0 else None

        while True:
            await self._cleanup_expired(conn)
            query = (
                "SELECT id, sender, recipient, body, thread_id, created_at "
                "FROM messages WHERE (recipient = ? OR recipient IS NULL)"
            )
            params = [self.agent_id]

            if not include_self:
                query += " AND sender != ?"
                params.append(self.agent_id)

            if unread_only:
                query += (
                    " AND NOT EXISTS "
                    "(SELECT 1 FROM reads WHERE agent_id = ? AND message_id = messages.id)"
                )
                params.append(self.agent_id)

            query += " ORDER BY created_at ASC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            if rows:
                # Mark as read
                ts = time.time()
                for row in rows:
                    await conn.execute(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) "
                        "VALUES (?, ?, ?)",
                        (self.agent_id, row["id"], ts),
                    )
                await conn.commit()

                return [dict(row) for row in rows]

            if not deadline:
                return []

            if time.time() >= deadline:
                return []

            await asyncio.sleep(0.1)

    async def peek(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Peek at recent messages without marking read.

        Args:
            limit: Max number of messages to return (default: 20)

        Returns:
            List of message dicts

        Raises:
            ValueError: If limit is not a positive integer
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        conn = await self._connect()
        await self._cleanup_expired(conn)
        cursor = await conn.execute(
            "SELECT id, sender, recipient, body, thread_id, created_at "
            "FROM messages ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]

    async def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search messages.

        Args:
            query: Search query substring
            limit: Max results

        Returns:
            List of matching message dicts

        Raises:
            ValueError: If query is empty or limit is not positive
        """
        if not query or not query.strip():
            raise ValueError("search query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, sender, recipient, body, thread_id, created_at "
            "FROM messages WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query.lower()}%", limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all messages in a thread.

        Args:
            thread_id: Thread ID (must not be empty)

        Returns:
            List of message dicts

        Raises:
            ValueError: If thread_id is empty or whitespace-only
        """
        if not thread_id or not thread_id.strip():
            raise ValueError("thread_id must not be empty")
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, sender, recipient, body, thread_id, created_at "
            "FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_peers(self) -> List[Dict[str, Any]]:
        """Get list of registered agents.

        Returns:
            List of peer dicts with id, role, status, cli
        """
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, role, cli, status FROM agents ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def set_status(self, status: str) -> None:
        """Update agent status.

        Args:
            status: Status (active, idle, done, blocked, etc.)

        Raises:
            ValueError: If status is not a valid value
        """
        valid_statuses = ("active", "idle", "done", "blocked")
        if status not in valid_statuses:
            raise ValueError(
                f"invalid status '{status}'. Must be one of {valid_statuses}"
            )
        conn = await self._connect()
        await conn.execute(
            "UPDATE agents SET status = ?, last_seen = ? WHERE id = ?",
            (status, time.time(), self.agent_id),
        )
        await conn.commit()

    async def get_status(self, agent_id: Optional[str] = None) -> Optional[str]:
        """Get agent status.

        Args:
            agent_id: Agent ID (defaults to self)

        Returns:
            Status string or None if not found
        """
        agent = agent_id or self.agent_id
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT status FROM agents WHERE id = ?", (agent,)
        )
        row = await cursor.fetchone()
        return row["status"] if row else None

    async def stats(self) -> Dict[str, Any]:
        """Get bus statistics.

        Returns:
            Stats dict with message/agent counts
        """
        conn = await self._connect()

        # Count messages
        cursor = await conn.execute("SELECT COUNT(*) as count FROM messages")
        messages = (await cursor.fetchone())["count"]

        # Count broadcasts
        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM messages WHERE recipient IS NULL"
        )
        broadcasts = (await cursor.fetchone())["count"]

        # Count threads
        cursor = await conn.execute(
            "SELECT COUNT(DISTINCT thread_id) as count "
            "FROM messages WHERE thread_id IS NOT NULL"
        )
        threads = (await cursor.fetchone())["count"]

        # Count agents by status
        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM agents WHERE status = 'active'"
        )
        agents_active = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM agents WHERE status = 'done'"
        )
        agents_done = (await cursor.fetchone())["count"]

        # Top senders
        cursor = await conn.execute(
            "SELECT sender, COUNT(*) as count FROM messages "
            "GROUP BY sender ORDER BY count DESC LIMIT 5"
        )
        top_senders = [
            {"agent": row["sender"], "count": row["count"]}
            for row in await cursor.fetchall()
        ]

        return {
            "messages": messages,
            "direct_messages": messages - broadcasts,
            "broadcasts": broadcasts,
            "threads": threads,
            "agents_active": agents_active,
            "agents_done": agents_done,
            "top_senders": top_senders,
        }

    async def wait_for_messages(
        self, count: int = 1, timeout: float = 60
    ) -> List[Dict[str, Any]]:
        """Wait for a specific number of messages.

        Args:
            count: Number of messages to wait for (must be positive)
            timeout: Max seconds to wait (must be non-negative, default: 60)

        Returns:
            List of message dicts

        Raises:
            ValueError: If count is not a positive integer or timeout is negative
        """
        if not isinstance(count, int) or count <= 0:
            raise ValueError("count must be a positive integer")
        if timeout < 0:
            raise ValueError("timeout must be a non-negative number of seconds")
        if not math.isfinite(timeout):
            raise ValueError("timeout must be a finite number")
        deadline = time.time() + timeout
        messages = []

        while len(messages) < count:
            if time.time() > deadline:
                break

            new_messages = await self.recv(wait=1, unread_only=True, limit=count)
            messages.extend(new_messages)

        return messages[:count]

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()


# Helper function for concurrent agent patterns
async def run_agent(agent_id: str, project: str, handler: Callable[..., Any]) -> None:
    """Run an async agent with automatic cleanup.

    Args:
        agent_id: Agent ID
        project: Project name
        handler: Async handler function that receives client
    """
    async with A2AClientAsync(project, agent_id) as client:
        await client.set_status("active")
        try:
            await handler(client)
        finally:
            await client.set_status("done")


# Helper for running multiple agents concurrently
async def run_agents(agents: List[tuple], handler: Callable[..., Any]) -> None:
    """Run multiple agents concurrently.

    Args:
        agents: List of (agent_id, project) tuples
        handler: Async handler function that receives client
    """
    tasks = [run_agent(agent_id, project, handler) for agent_id, project in agents]
    await asyncio.gather(*tasks)
