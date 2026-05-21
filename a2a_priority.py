#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Message Prioritization — Priority-aware message queuing and delivery (v1.3).

Enables priority levels (critical, high, normal, low) with automatic queue ordering.
Supports priority-based recv() and filtering by importance.
"""

import time
from typing import Optional, List, Dict, Any
from enum import IntEnum

from a2a_client import A2AClient


class Priority(IntEnum):
    """Message priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_string(cls, value: str) -> "Priority":
        """Convert string to priority level.

        Args:
            value: Priority name (critical, high, normal, low)

        Returns:
            Priority enum value
        """
        name = value.upper()
        if name in cls.__members__:
            return cls[name]
        return cls.NORMAL


class PriorityClient(A2AClient):
    """Client with priority-aware message handling."""

    def __init__(self, project: str, agent_id: str):
        """Initialize priority client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        super().__init__(project, agent_id)

    def init_priority_table(self) -> bool:
        """Add priority column to messages table if not exists.

        Returns:
            True if successful, False on error
        """
        conn = self._connect()
        try:
            # Check if priority column exists
            cursor = conn.execute("PRAGMA table_info(messages)")
            columns = {row[1] for row in cursor.fetchall()}

            if "priority" not in columns:
                # Add priority column with default value
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN priority INTEGER DEFAULT 2"
                )
                conn.commit()

            # Create index for priority queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_priority ON messages(priority)"
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing priority: {e}")
            return False
        finally:
            conn.close()

    def send(
        self,
        to: str,
        message: str,
        priority: int = Priority.NORMAL,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """Send a message with priority.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            priority: Priority level (1=LOW, 2=NORMAL, 3=HIGH, 4=CRITICAL)
            ttl_seconds: Optional time-to-live in seconds

        Returns:
            Message ID
        """
        conn = self._connect()
        try:
            recipient = None if to.lower() in ("all", "*", "broadcast") else to
            cur = conn.execute(
                "INSERT INTO messages(sender, recipient, body, priority, ttl_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, priority, ttl_seconds, time.time()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def recv(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
        priority_aware: bool = True,
    ) -> List[Dict[str, Any]]:
        """Receive messages with optional priority ordering.

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)
            priority_aware: Order by priority (highest first), then timestamp

        Returns:
            List of message dicts ordered by priority (if priority_aware)
        """
        conn = self._connect()
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

                cursor = conn.execute(base, params)
                messages = [dict(row) for row in cursor.fetchall()]

                if messages:
                    return messages

                if wait <= 0:
                    return []

                if deadline and time.time() >= deadline:
                    return []

                time.sleep(poll_interval)
        finally:
            conn.close()

    def recv_by_priority(
        self,
        priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages of specific priority level.

        Args:
            priority: Priority level to receive
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of message dicts with specified priority
        """
        conn = self._connect()
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

                cursor = conn.execute(base, params)
                messages = [dict(row) for row in cursor.fetchall()]

                if messages:
                    return messages

                if wait <= 0:
                    return []

                if deadline and time.time() >= deadline:
                    return []

                time.sleep(poll_interval)
        finally:
            conn.close()

    def recv_above_priority(
        self,
        min_priority: int,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages with priority >= min_priority.

        Args:
            min_priority: Minimum priority level (inclusive)
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of message dicts ordered by priority desc, then timestamp asc
        """
        conn = self._connect()
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

                cursor = conn.execute(base, params)
                messages = [dict(row) for row in cursor.fetchall()]

                if messages:
                    return messages

                if wait <= 0:
                    return []

                if deadline and time.time() >= deadline:
                    return []

                time.sleep(poll_interval)
        finally:
            conn.close()

    def get_priority_stats(self) -> Dict[str, Any]:
        """Get statistics on message priorities.

        Returns:
            Dict with priority distribution
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT priority, COUNT(*) as count
                FROM messages
                GROUP BY priority
                ORDER BY priority DESC
            """
            )

            stats = {}
            for row in cursor.fetchall():
                priority_level = Priority(row[0]).name
                stats[priority_level] = row[1]

            return stats
        finally:
            conn.close()

    def get_priority_stats_by_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get priority statistics for messages from specific agent.

        Args:
            agent_id: Agent to analyze

        Returns:
            Dict with priority distribution
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
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
            for row in cursor.fetchall():
                priority_level = Priority(row[0]).name
                stats[priority_level] = row[1]

            return stats
        finally:
            conn.close()

    def mark_read(self, message_id: int) -> bool:
        """Mark message as read.

        Args:
            message_id: Message to mark as read

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) "
                "VALUES (?, ?, ?)",
                (self.agent_id, message_id, time.time()),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error marking as read: {e}")
            return False
        finally:
            conn.close()

    def get_critical_messages(
        self, unread_only: bool = True, include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all critical priority messages.

        Args:
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent

        Returns:
            List of critical priority messages
        """
        return self.recv_by_priority(
            Priority.CRITICAL,
            unread_only=unread_only,
            include_self=include_self,
        )

    def get_high_priority_messages(
        self, unread_only: bool = True, include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all high and critical priority messages.

        Args:
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent

        Returns:
            List of high/critical messages ordered by priority
        """
        return self.recv_above_priority(
            Priority.HIGH,
            unread_only=unread_only,
            include_self=include_self,
        )


class PriorityQueue:
    """Helper class for managing a priority-based message queue."""

    def __init__(self, client: PriorityClient, agent_id: str):
        """Initialize priority queue.

        Args:
            client: PriorityClient instance
            agent_id: Agent receiving messages
        """
        self.client = client
        self.agent_id = agent_id
        self.queue = []

    def poll(self, wait: float = 0, limit: int = 0) -> List[Dict[str, Any]]:
        """Poll for messages and maintain priority queue.

        Args:
            wait: Block up to N seconds for new messages
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of messages ordered by priority
        """
        messages = self.client.recv(
            wait=wait, unread_only=True, limit=limit, priority_aware=True
        )
        self.queue.extend(messages)

        # Return up to limit items
        if limit:
            result = self.queue[:limit]
            self.queue = self.queue[limit:]
        else:
            result = self.queue
            self.queue = []

        return result

    def peek_critical(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Peek at critical messages without marking as read.

        Args:
            limit: Max messages to return

        Returns:
            List of critical messages
        """
        conn = self.client._connect()
        try:
            cursor = conn.execute(
                """
                SELECT m.id, m.sender, m.recipient, m.body, m.thread_id,
                       m.priority, m.created_at FROM messages m
                WHERE (m.recipient = ? OR m.recipient IS NULL)
                AND m.sender != ?
                AND m.priority = ?
                AND NOT EXISTS (SELECT 1 FROM reads r
                    WHERE r.agent_id = ? AND r.message_id = m.id)
                ORDER BY m.created_at ASC
                LIMIT ?
            """,
                (self.agent_id, self.agent_id, Priority.CRITICAL, self.agent_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
