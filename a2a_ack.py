#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Message Acknowledgment Protocol — Reliable message delivery tracking (v1.5).

Tracks which messages have been acknowledged by their recipients.
Provides auto-acknowledgment on recv() and query for pending acknowledgments.
"""

import time
from typing import Optional, List, Dict, Any

from a2a_client import A2AClient


class AckClient(A2AClient):
    """Client with message acknowledgment support."""

    def init_ack_table(self) -> bool:
        """Create acknowledgments table if not exists.

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acknowledgments (
                    message_id  INTEGER NOT NULL,
                    agent_id    TEXT NOT NULL,
                    acked_at    REAL NOT NULL,
                    PRIMARY KEY (message_id, agent_id)
                )
            """)
            # Add requires_ack column to messages if missing
            try:
                conn.execute("SELECT requires_ack FROM messages WHERE 1=0")
            except Exception:
                conn.execute("ALTER TABLE messages ADD COLUMN requires_ack INTEGER DEFAULT 0")
            # Add priority column to messages if missing
            try:
                conn.execute("SELECT priority FROM messages WHERE 1=0")
            except Exception:
                conn.execute("ALTER TABLE messages ADD COLUMN priority INTEGER DEFAULT 2")
            conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing ack table: {e}")
            return False
        finally:
            conn.close()

    def send(
        self,
        to: str,
        message: str,
        ttl_seconds: Optional[int] = None,
        thread_id: Optional[str] = None,
        require_ack: bool = False,
        priority: int = 2,
    ) -> int:
        """Send a message, optionally requiring acknowledgment.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            ttl_seconds: Optional time-to-live in seconds
            thread_id: Optional thread ID
            require_ack: If True, recipient must acknowledge receipt
            priority: Message priority (1=LOW, 2=NORMAL, 3=HIGH, 4=URGENT)

        Returns:
            Message ID
        """
        conn = self._connect()
        try:
            if not to or not to.strip():
                raise ValueError("recipient must not be empty")
            if ttl_seconds is not None and ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be a positive number of seconds")
            if thread_id is not None and not thread_id.strip():
                raise ValueError("thread_id must not be empty")
            if priority < 1 or priority > 4:
                raise ValueError(f"priority must be 1-4, got {priority}")
            if require_ack and to.lower() in ("all", "*", "broadcast"):
                raise ValueError("cannot require acknowledgment for broadcast messages")

            # Validate sender is registered
            cur = conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (self.agent_id,))
            if cur.fetchone()[0] == 0:
                raise ValueError(f"unknown sender '{self.agent_id}' — register first")

            recipient = None if to.lower() in ("all", "*", "broadcast") else to
            if recipient is not None:
                cur = conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (recipient,))
                if cur.fetchone()[0] == 0:
                    raise ValueError(f"unknown recipient '{recipient}' — register them first")

            requires_ack_val = 1 if require_ack else 0
            cur = conn.execute(
                "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, priority, requires_ack, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, thread_id, ttl_seconds, priority, requires_ack_val, time.time()),
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
        auto_ack: bool = True,
    ) -> List[Dict[str, Any]]:
        """Receive messages, optionally auto-acknowledging.

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)
            auto_ack: Automatically acknowledge messages that require it

        Returns:
            List of message dicts ordered by priority (highest first)
        """
        conn = self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                self._cleanup_expired(conn)
                base = (
                    "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                    "m.priority, m.requires_ack, m.created_at FROM messages m "
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

                base += "ORDER BY m.priority DESC, m.created_at ASC "

                if limit:
                    base += "LIMIT ?"
                    params.append(limit)

                cursor = conn.execute(base, params)
                messages = [dict(row) for row in cursor.fetchall()]

                if messages:
                    ts = time.time()
                    # Mark as read
                    conn.executemany(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
                        [(self.agent_id, m["id"], ts) for m in messages],
                    )
                    # Auto-acknowledge if required
                    if auto_ack:
                        for m in messages:
                            if m.get("requires_ack"):
                                conn.execute(
                                    "INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?,?,?)",
                                    (m["id"], self.agent_id, ts),
                                )
                    conn.commit()
                    return messages

                if wait <= 0:
                    return []

                if deadline and time.time() >= deadline:
                    return []

                time.sleep(poll_interval)
        finally:
            conn.close()

    def ack(self, message_id: int) -> bool:
        """Acknowledge receipt of a specific message.

        Args:
            message_id: Message to acknowledge

        Returns:
            True if acknowledged
        """
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?,?,?)",
                (message_id, self.agent_id, time.time()),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error acknowledging message: {e}")
            return False
        finally:
            conn.close()

    def ack_message(self, message_id: int) -> bool:
        """Alias for ack()."""
        return self.ack(message_id)

    def get_pending_acks(self) -> List[Dict[str, Any]]:
        """Get messages requiring acknowledgment that haven't been acked yet.

        Returns:
            List of messages pending acknowledgment
        """
        conn = self._connect()
        try:
            self._cleanup_expired(conn)
            cursor = conn.execute(
                "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                "m.priority, m.requires_ack, m.created_at FROM messages m "
                "WHERE m.requires_ack = 1 "
                "AND m.recipient = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM acknowledgments a "
                "  WHERE a.message_id = m.id AND a.agent_id = ?"
                ") "
                "ORDER BY m.created_at ASC",
                (self.agent_id, self.agent_id),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_ack_status(self, message_id: int) -> Dict[str, Any]:
        """Get acknowledgment status for a message.

        Args:
            message_id: Message to check

        Returns:
            Dict with ack info
        """
        conn = self._connect()
        try:
            msg = conn.execute(
                "SELECT id, sender, recipient, requires_ack FROM messages WHERE id=?",
                (message_id,),
            ).fetchone()
            if not msg:
                return {"error": "message not found"}
            msg = dict(msg)
            if not msg.get("requires_ack"):
                return {"message_id": message_id, "requires_ack": False, "acked": False}
            ack = conn.execute(
                "SELECT agent_id, acked_at FROM acknowledgments WHERE message_id=?",
                (message_id,),
            ).fetchone()
            if ack:
                return {
                    "message_id": message_id,
                    "requires_ack": True,
                    "acked": True,
                    "agent_id": ack["agent_id"],
                    "acked_at": ack["acked_at"],
                }
            return {"message_id": message_id, "requires_ack": True, "acked": False}
        finally:
            conn.close()

    def wait_for_ack(self, message_id: int, timeout: float = 30.0, poll: float = 0.5) -> bool:
        """Wait for a message to be acknowledged.

        Args:
            message_id: Message to wait on
            timeout: Max seconds to wait
            poll: Poll interval in seconds

        Returns:
            True if acked before timeout
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_ack_status(message_id)
            if status.get("acked"):
                return True
            time.sleep(poll)
        return False

    def mark_read(self, message_id: int) -> bool:
        """Mark a message as read."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
                (self.agent_id, message_id, time.time()),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error marking message as read: {e}")
            return False
        finally:
            conn.close()


class AckContextManager:
    """Context manager that auto-acknowledges messages on exit.

    Usage:
        with AckContextManager(client, message_id) as ack:
            # process message
            if error:
                ack.failed = True
        # auto-acks (or marks as failed) on exit
    """

    def __init__(self, client: AckClient, message_id: int):
        self.client = client
        self.message_id = message_id
        self.failed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None or self.failed:
            self.client.mark_read(self.message_id)
        else:
            self.client.ack(self.message_id)
        return False
