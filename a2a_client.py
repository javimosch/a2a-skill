#!/usr/bin/env python3
"""
a2a Client Library — Python API for a2a peer messaging.

Provides object-oriented access to a2a messaging without shell invocation.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any


class A2AClient:
    """Client for a2a peer-to-peer messaging."""

    def __init__(self, project: str, agent_id: str):
        """Initialize a2a client.

        Args:
            project: Project name (or env A2A_PROJECT)
            agent_id: This agent's ID
        """
        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"

    def _connect(self) -> sqlite3.Connection:
        """Connect to project database."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def send(self, to: str, message: str, ttl_seconds: Optional[int] = None) -> int:
        """Send a message.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            ttl_seconds: Optional time-to-live in seconds

        Returns:
            Message ID
        """
        conn = self._connect()
        try:
            recipient = None if to.lower() in ("all", "*", "broadcast") else to
            cur = conn.execute(
                "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, ttl_seconds, time.time()),
            )
            conn.commit()
            msg_id = cur.lastrowid
            return msg_id
        finally:
            conn.close()

    def recv(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)

        Returns:
            List of message dicts
        """
        conn = self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                # Build query
                base = (
                    "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, "
                    "m.created_at FROM messages m "
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

                base += "ORDER BY m.created_at ASC"
                if limit:
                    base += " LIMIT ?"
                    params.append(limit)

                rows = conn.execute(base, params).fetchall()

                if rows:
                    # Mark as read
                    ts = time.time()
                    conn.executemany(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
                        [(self.agent_id, r["id"], ts) for r in rows],
                    )
                    conn.commit()
                    return [dict(r) for r in rows]

                if not wait or (deadline and time.time() >= deadline):
                    return []

                time.sleep(poll_interval)
        finally:
            conn.close()

    def peek(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Peek at recent messages without marking read.

        Args:
            limit: Max messages to return

        Returns:
            List of message dicts
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, created_at "
                "FROM messages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def list_peers(self) -> List[Dict[str, Any]]:
        """Get list of registered agents.

        Returns:
            List of agent dicts with id, role, status, etc.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, role, cli, status, pid FROM agents ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def set_status(self, status: str) -> None:
        """Update this agent's status.

        Args:
            status: One of 'active', 'idle', 'done', 'blocked'
        """
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE agents SET status=?, last_seen=? WHERE id=?",
                (status, time.time(), self.agent_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_status(self, agent_id: Optional[str] = None) -> Optional[str]:
        """Get an agent's status.

        Args:
            agent_id: Agent ID (defaults to self.agent_id)

        Returns:
            Status string or None if agent not found
        """
        agent = agent_id or self.agent_id
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status FROM agents WHERE id=?", (agent,)
            ).fetchone()
            return row["status"] if row else None
        finally:
            conn.close()

    def wait_for_messages(
        self, count: int = 1, timeout: float = 60
    ) -> bool:
        """Block until N unread messages or timeout.

        Args:
            count: Number of unread messages to wait for
            timeout: Max seconds to wait

        Returns:
            True if got N messages, False on timeout
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            messages = self.recv(unread_only=True)
            if len(messages) >= count:
                return True
            time.sleep(0.5)
        return False


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 a2a_client.py <project> <agent-id>")
        print("")
        print("Example:")
        print("  from a2a_client import A2AClient")
        print("  client = A2AClient('my-project', 'alice')")
        print("  client.send('bob', 'Hello')")
        print("  messages = client.recv(wait=10)")
        sys.exit(1)

    project = sys.argv[1]
    agent_id = sys.argv[2]

    client = A2AClient(project, agent_id)

    print(f"A2A Client initialized")
    print(f"  Project: {project}")
    print(f"  Agent: {agent_id}")
    print(f"  Database: {client.db_path}")
    print("")
    print("Available methods:")
    print("  client.send(to, message, ttl_seconds=None)")
    print("  client.recv(wait=0, unread_only=True, include_self=False, limit=0)")
    print("  client.peek(limit=20)")
    print("  client.list_peers()")
    print("  client.set_status(status)")
    print("  client.get_status(agent_id=None)")
    print("  client.wait_for_messages(count=1, timeout=60)")
