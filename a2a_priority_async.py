#!/usr/bin/env python3
"""
a2a Async Message Prioritization — High-performance priority-aware messaging (v1.3).

Non-blocking async version using aiosqlite for concurrent priority operations.
Full API parity with a2a_priority.PriorityClient.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

from pathlib import Path
from enum import IntEnum

from a2a_priority import Priority, PriorityClient


class PriorityClientAsync:
    """Async client with priority-aware message handling."""

    def __init__(self, project: str, agent_id: str):
        """Initialize async priority client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        if not HAS_AIOSQLITE:
            raise ImportError(
                "aiosqlite library required: pip install aiosqlite"
            )

        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"

    async def _connect(self) -> aiosqlite.Connection:
        """Connect to database asynchronously."""
        conn = await aiosqlite.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = aiosqlite.Row
        return conn

    async def init_priority_table(self) -> bool:
        """Add priority column to messages table if not exists.

        Returns:
            True if successful, False on error
        """
        conn = await self._connect()
        try:
            # Check if priority column exists
            cursor = await conn.execute("PRAGMA table_info(messages)")
            columns = {row[1] async for row in cursor}

            if "priority" not in columns:
                # Add priority column with default value
                await conn.execute(
                    "ALTER TABLE messages ADD COLUMN priority INTEGER DEFAULT 2"
                )
                await conn.commit()

            # Create index for priority queries
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_priority ON messages(priority)"
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing priority: {e}")
            return False
        finally:
            await conn.close()

    async def send(
        self,
        to: str,
        message: str,
        priority: int = Priority.NORMAL,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """Send a message with priority (async).

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            priority: Priority level (1=LOW, 2=NORMAL, 3=HIGH, 4=CRITICAL)
            ttl_seconds: Optional time-to-live in seconds

        Returns:
            Message ID
        """
        conn = await self._connect()
        try:
            recipient = None if to.lower() in ("all", "*", "broadcast") else to
            cursor = await conn.execute(
                "INSERT INTO messages(sender, recipient, body, priority, ttl_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, priority, ttl_seconds, time.time()),
            )
            await conn.commit()
            return cursor.lastrowid
        finally:
            await conn.close()

    async def recv(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
        priority_aware: bool = True,
    ) -> List[Dict[str, Any]]:
        """Receive messages with optional priority ordering (async).

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)
            priority_aware: Order by priority (highest first), then timestamp

        Returns:
            List of message dicts ordered by priority (if priority_aware)
        """
        conn = await self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                # Build query
                base = (
                    "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                    "m.priority, m.created_at FROM messages m "
                    "WHERE (m.recipient = ? OR m.recipient IS NULL) "
                )
                params = [self.agent_id]

                if not include_self:
                    base += "AND m.sender != ? "
                    params.append(self.agent_id)

                if unread_only:
                    base += (
                        "AND NOT EXISTS (SELECT 1 FROM reads r "
                        "WHERE r.agent_id = ? AND r.message_id = m.id) "
                    )
                    params.append(self.agent_id)

                # Order by priority (desc) then timestamp (asc)
                if priority_aware:
                    base += "ORDER BY m.priority DESC, m.created_at ASC "
                else:
                    base += "ORDER BY m.created_at ASC "

                if limit:
                    base += "LIMIT ?"
                    params.append(limit)

                cursor = await conn.execute(base, params)
                messages = []
                async for row in cursor:
                    messages.append(dict(row))

                if messages:
                    return messages

                if deadline and time.time() >= deadline:
                    return []

                await asyncio.sleep(poll_interval)
        finally:
            await conn.close()

    async def recv_by_priority(
        self,
        priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages of specific priority level (async).

        Args:
            priority: Priority level to receive
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of message dicts with specified priority
        """
        conn = await self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                base = (
                    "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                    "m.priority, m.created_at FROM messages m "
                    "WHERE (m.recipient = ? OR m.recipient IS NULL) "
                    "AND m.priority = ? "
                )
                params = [self.agent_id, priority]

                if not include_self:
                    base += "AND m.sender != ? "
                    params.append(self.agent_id)

                if unread_only:
                    base += (
                        "AND NOT EXISTS (SELECT 1 FROM reads r "
                        "WHERE r.agent_id = ? AND r.message_id = m.id) "
                    )
                    params.append(self.agent_id)

                base += "ORDER BY m.created_at ASC "

                if limit:
                    base += "LIMIT ?"
                    params.append(limit)

                cursor = await conn.execute(base, params)
                messages = []
                async for row in cursor:
                    messages.append(dict(row))

                if messages:
                    return messages

                if deadline and time.time() >= deadline:
                    return []

                await asyncio.sleep(poll_interval)
        finally:
            await conn.close()

    async def recv_above_priority(
        self,
        min_priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages with priority >= min_priority (async).

        Args:
            min_priority: Minimum priority level (inclusive)
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of message dicts ordered by priority desc, then timestamp asc
        """
        conn = await self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                base = (
                    "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                    "m.priority, m.created_at FROM messages m "
                    "WHERE (m.recipient = ? OR m.recipient IS NULL) "
                    "AND m.priority >= ? "
                )
                params = [self.agent_id, min_priority]

                if not include_self:
                    base += "AND m.sender != ? "
                    params.append(self.agent_id)

                if unread_only:
                    base += (
                        "AND NOT EXISTS (SELECT 1 FROM reads r "
                        "WHERE r.agent_id = ? AND r.message_id = m.id) "
                    )
                    params.append(self.agent_id)

                base += "ORDER BY m.priority DESC, m.created_at ASC "

                if limit:
                    base += "LIMIT ?"
                    params.append(limit)

                cursor = await conn.execute(base, params)
                messages = []
                async for row in cursor:
                    messages.append(dict(row))

                if messages:
                    return messages

                if deadline and time.time() >= deadline:
                    return []

                await asyncio.sleep(poll_interval)
        finally:
            await conn.close()

    async def get_priority_stats(self) -> Dict[str, Any]:
        """Get statistics on message priorities (async).

        Returns:
            Dict with priority distribution
        """
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                """
                SELECT priority, COUNT(*) as count
                FROM messages
                GROUP BY priority
                ORDER BY priority DESC
            """
            )

            stats = {}
            async for row in cursor:
                priority_level = Priority(row[0]).name
                stats[priority_level] = row[1]

            return stats
        finally:
            await conn.close()

    async def get_priority_stats_by_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get priority statistics for messages from specific agent (async).

        Args:
            agent_id: Agent to analyze

        Returns:
            Dict with priority distribution
        """
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                """
                SELECT priority, COUNT(*) as count
                FROM messages
                WHERE sender = ?
                GROUP BY priority
                ORDER BY priority DESC
            """,
                (agent_id,),
            )

            stats = {}
            async for row in cursor:
                priority_level = Priority(row[0]).name
                stats[priority_level] = row[1]

            return stats
        finally:
            await conn.close()

    async def mark_read(self, message_id: int) -> bool:
        """Mark message as read (async).

        Args:
            message_id: Message to mark as read

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) "
                "VALUES (?, ?, ?)",
                (self.agent_id, message_id, time.time()),
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Error marking as read: {e}")
            return False
        finally:
            await conn.close()

    async def get_critical_messages(
        self, unread_only: bool = True, include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all critical priority messages (async).

        Args:
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent

        Returns:
            List of critical priority messages
        """
        return await self.recv_by_priority(
            Priority.CRITICAL,
            unread_only=unread_only,
            include_self=include_self,
        )

    async def get_high_priority_messages(
        self, unread_only: bool = True, include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all high and critical priority messages (async).

        Args:
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent

        Returns:
            List of high/critical messages ordered by priority
        """
        return await self.recv_above_priority(
            Priority.HIGH,
            unread_only=unread_only,
            include_self=include_self,
        )


async def run_agents(agents: List) -> List:
    """Run multiple async priority agents concurrently.

    Args:
        agents: List of coroutines to run

    Returns:
        List of results
    """
    return await asyncio.gather(*agents)
