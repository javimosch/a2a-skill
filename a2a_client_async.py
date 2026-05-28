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

from a2a_common import MAX_ID_LENGTH, MAX_ROLE_LENGTH, MAX_THREAD_ID_LENGTH, MAX_BODY_LENGTH
from a2a_common import _validate_project_name, _validate_agent_id


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
        _validate_project_name(project)
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        _validate_agent_id(agent_id, 'agent_id')
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
        # Validate sender is registered
        cur = await conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (self.agent_id,))
        row = await cur.fetchone()
        if row[0] == 0:
            raise ValueError(f"unknown sender '{self.agent_id}' — register first")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive number of seconds")
        if ttl_seconds is not None and (math.isnan(ttl_seconds) or math.isinf(ttl_seconds)):
            raise ValueError("ttl_seconds must be a finite number")
        if thread_id is not None and not thread_id.strip():
            raise ValueError("thread_id must not be empty")
        if thread_id is not None and len(thread_id) > MAX_THREAD_ID_LENGTH:
            raise ValueError(f"thread_id too long ({len(thread_id)} chars, max {MAX_THREAD_ID_LENGTH})")
        if not message or not message.strip():
            raise ValueError("message body must not be empty")
        if len(message) > MAX_BODY_LENGTH:
            raise ValueError(f"message body too long ({len(message)} chars, max {MAX_BODY_LENGTH})")
        recipient = None if to.lower() in ("all", "*", "broadcast") else to
        if recipient is not None:
            cur = await conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (recipient,))
            row = await cur.fetchone()
            if row[0] == 0:
                raise ValueError(f"unknown recipient '{recipient}' — register them first")
        cursor = await conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.agent_id, recipient, message, thread_id, ttl_seconds, time.time()),
        )
        msg_id = cursor.lastrowid
        await conn.commit()
        return msg_id

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
            upsert: Update existing registration if True (preserves created_at)

        Returns:
            True on success
        """
        if pid is not None and pid <= 0:
            raise ValueError("pid must be a positive integer")
        if len(role) > MAX_ROLE_LENGTH:
            raise ValueError(f"role too long ({len(role)} chars, max {MAX_ROLE_LENGTH})")
        if len(cli) > 128:
            raise ValueError(f"cli too long ({len(cli)} chars, max 128)")
        if len(prompt) > MAX_BODY_LENGTH:
            raise ValueError(f"prompt too long ({len(prompt)} chars, max {MAX_BODY_LENGTH})")
        conn = await self._connect()
        now = time.time()
        if upsert:
            await conn.execute(
                "INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent_id, role, prompt, cli, "active", pid, now, now),
            )
            await conn.execute(
                "UPDATE agents SET role=COALESCE(NULLIF(?,''),role), prompt=COALESCE(NULLIF(?,''),prompt), "
                "cli=COALESCE(NULLIF(?,''),cli), pid=COALESCE(?,pid), status='active', last_seen=? "
                "WHERE id=?",
                (role, prompt, cli, pid, now, self.agent_id),
            )
        else:
            await conn.execute(
                "INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent_id, role, prompt, cli, "active", pid, now, now),
            )
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
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Max seconds to wait for messages (supports fractional)
            unread_only: Only return unread messages
            include_self: Include messages from self
            limit: Max number of messages to return (0 = unlimited)

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
        if limit < 0:
            raise ValueError("limit must be a non-negative integer")
        deadline = time.time() + wait if wait > 0 else None

        while True:
            await self._cleanup_expired(conn)
            await conn.commit()
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
            if limit > 0:
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
        await conn.commit()
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

    async def list(self) -> List[Dict[str, Any]]:
        """Get list of registered agents (alias for list_peers).

        Returns:
            List of peer dicts with id, role, status, cli
        """
        return await self.list_peers()

    async def list_peers(self) -> List[Dict[str, Any]]:
        """Get list of registered agents.

        Returns:
            List of peer dicts with id, role, status, cli
        """
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, role, cli, status, pid FROM agents ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def status(self, new_status: Optional[str] = None) -> Optional[str]:
        """Get or set this agent's status.

        Args:
            new_status: If provided, set status. Omit to get current status.

        Returns:
            Current status string when getting, None when setting.
        """
        if new_status is not None:
            await self.set_status(new_status)
            return None
        return await self.get_status()

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

    async def wait(
        self, count: int = 1, timeout: float = 60
    ) -> bool:
        """Wait for N unread messages or timeout (alias for wait_for_messages).

        Args:
            count: Number of unread messages to wait for (must be positive)
            timeout: Max seconds to wait (must be non-negative, default: 60)

        Returns:
            True if got N messages, False on timeout
        """
        return await self.wait_for_messages(count, timeout)

    async def wait_for_messages(
        self, count: int = 1, timeout: float = 60
    ) -> bool:
        """Block until N unread messages or timeout.

        Args:
            count: Number of unread messages to wait for (must be positive)
            timeout: Max seconds to wait (must be non-negative, default: 60)

        Returns:
            True if got N messages, False on timeout

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
        seen = []

        while time.time() < deadline:
            new_messages = await self.recv(wait=0, unread_only=True)
            seen.extend(new_messages)
            if len(seen) >= count:
                return True
            if not new_messages:
                await asyncio.sleep(0.5)

        return False

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def init_project(self) -> None:
        """Initialize the project database, creating tables if they don't exist.

        Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
        """
        conn = await self._connect()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id          TEXT PRIMARY KEY,
                role        TEXT,
                prompt      TEXT,
                cli         TEXT,
                status      TEXT NOT NULL DEFAULT 'active',
                pid         INTEGER,
                created_at  REAL NOT NULL,
                last_seen   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sender      TEXT NOT NULL,
                recipient   TEXT,
                body        TEXT NOT NULL,
                thread_id   TEXT,
                ttl_seconds INTEGER,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reads (
                agent_id    TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                read_at     REAL NOT NULL,
                PRIMARY KEY (agent_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
            CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);
        """)
        await conn.commit()

    def project_info(self) -> Dict[str, Any]:
        """Get resolved project information.

        Returns:
            Dict with project name, database path, and whether the DB exists.
        """
        return {
            "project": self.project,
            "db": str(self.db_path),
            "exists": self.db_path.exists(),
        }

    async def clear(self) -> None:
        """Delete the project database and all WAL-related files.

        Warning: This permanently deletes all messages and agent registrations.
        """
        await self.close()
        from pathlib import Path as _Path
        for suffix in ("", "-wal", "-shm"):
            p = _Path(str(self.db_path) + suffix)
            if p.exists():
                p.unlink()


# Helper function for concurrent agent patterns
async def run_agent(
    agent_id: str,
    project: str,
    handler: Callable[..., Any],
    role: str = "",
    prompt: str = "",
    cli: str = "",
) -> None:
    """Run an async agent with automatic cleanup.

    Args:
        agent_id: Agent ID
        project: Project name
        handler: Async handler function that receives client
        role: Optional agent role (registered before setting active)
        prompt: Optional agent prompt
        cli: Optional CLI identifier
    """
    async with A2AClientAsync(project, agent_id) as client:
        await client.register(role, prompt, cli)
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
