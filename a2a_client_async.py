#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Async Client Library — Asyncio-based API for high-performance a2a messaging.

Provides async/await interface for concurrent agent patterns.
"""

import aiosqlite
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Any


class A2AClientAsync:
    """Async client for a2a peer-to-peer messaging."""

    def __init__(self, project: str, agent_id: str):
        """Initialize async a2a client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"
        self._conn: Optional[aiosqlite.Connection] = None

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
        self, to: str, message: str, ttl_seconds: Optional[int] = None
    ) -> int:
        """Send a message.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            ttl_seconds: Optional time-to-live in seconds

        Returns:
            Message ID
        """
        conn = await self._connect()
        recipient = None if to.lower() in ("all", "*", "broadcast") else to
        await conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.agent_id, recipient, message, ttl_seconds, time.time()),
        )
        await conn.commit()
        cursor = await conn.execute("SELECT last_insert_rowid() as id")
        row = await cursor.fetchone()
        return row["id"] if row else 0

    async def recv(
        self,
        wait: int = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Max seconds to wait for messages
            unread_only: Only return unread messages
            include_self: Include messages from self
            limit: Max number of messages to return

        Returns:
            List of message dicts
        """
        conn = await self._connect()
        deadline = time.time() + wait if wait > 0 else None

        while True:
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

            if deadline and time.time() >= deadline:
                return []

            await asyncio.sleep(0.1)

    async def peek(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Peek at recent messages without marking read.

        Args:
            limit: Max number of messages to return

        Returns:
            List of message dicts
        """
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, sender, recipient, body, thread_id, created_at "
            "FROM messages ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]

    async def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search messages.

        Args:
            query: Search query substring
            limit: Max results

        Returns:
            List of matching message dicts
        """
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT id, sender, recipient, body, thread_id, created_at "
            "FROM messages WHERE body LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all messages in a thread.

        Args:
            thread_id: Thread ID

        Returns:
            List of message dicts
        """
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
        """
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
        top_senders = [dict(row) for row in await cursor.fetchall()]

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
        self, count: int = 1, timeout: int = 30
    ) -> List[Dict[str, Any]]:
        """Wait for a specific number of messages.

        Args:
            count: Number of messages to wait for
            timeout: Max seconds to wait

        Returns:
            List of message dicts
        """
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
async def run_agent(agent_id: str, project: str, handler):
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
async def run_agents(agents: List[tuple], handler):
    """Run multiple agents concurrently.

    Args:
        agents: List of (agent_id, project) tuples
        handler: Async handler function that receives client
    """
    tasks = [run_agent(agent_id, project, handler) for agent_id, project in agents]
    await asyncio.gather(*tasks)
