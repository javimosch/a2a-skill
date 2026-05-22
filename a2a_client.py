#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

        Raises:
            ValueError: If project or agent_id is empty
        """
        if not project or not project.strip():
            raise ValueError("project must not be empty")
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"

    def _connect(self) -> sqlite3.Connection:
        """Connect to project database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def _cleanup_expired(conn: sqlite3.Connection) -> int:
        """Delete messages past their TTL. Return count deleted."""
        ts = time.time()
        cur = conn.execute(
            "DELETE FROM messages WHERE ttl_seconds IS NOT NULL "
            "AND created_at + ttl_seconds < ?",
            (ts,)
        )
        return cur.rowcount

    def send(
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
            ValueError: If recipient is empty
        """
        conn = self._connect()
        try:
            if not to or not to.strip():
                raise ValueError("recipient must not be empty")
            if ttl_seconds is not None and ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be a positive number of seconds")
            recipient = None if to.lower() in ("all", "*", "broadcast") else to
            cur = conn.execute(
                "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, thread_id, ttl_seconds, time.time()),
            )
            conn.commit()
            msg_id = cur.lastrowid
            return msg_id
        finally:
            conn.close()

    def register(
        self,
        role: str,
        prompt: str = "",
        cli: str = "",
        pid: int = 0,
        upsert: bool = True,
    ) -> bool:
        """Register this agent on the bus.

        Args:
            role: Agent's role description
            prompt: System prompt (optional)
            cli: CLI tool name (optional)
            pid: Process ID (optional)
            upsert: Update existing registration if True (preserves created_at)

        Returns:
            True on success
        """
        conn = self._connect()
        try:
            now = time.time()
            if upsert:
                conn.execute(
                    "INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (self.agent_id, role, prompt, cli, "active", pid, now, now),
                )
                conn.execute(
                    "UPDATE agents SET role=COALESCE(?,role), prompt=COALESCE(?,prompt), "
                    "cli=COALESCE(?,cli), pid=COALESCE(?,pid), status='active', last_seen=? "
                    "WHERE id=?",
                    (role, prompt, cli, pid, now, self.agent_id),
                )
            else:
                conn.execute(
                    "INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (self.agent_id, role, prompt, cli, "active", pid, now, now),
                )
            conn.commit()
            return True
        finally:
            conn.close()

    def unregister(self) -> bool:
        """Remove this agent from the bus.

        Returns:
            True on success
        """
        conn = self._connect()
        try:
            conn.execute("DELETE FROM agents WHERE id = ?", (self.agent_id,))
            conn.commit()
            return True
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
                self._cleanup_expired(conn)
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
            limit: Max messages to return (default: 20)

        Returns:
            List of message dicts

        Raises:
            ValueError: If limit is not a positive integer
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        conn = self._connect()
        try:
            self._cleanup_expired(conn)
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

        Raises:
            ValueError: If status is not a valid value
        """
        valid_statuses = ("active", "idle", "done", "blocked")
        if status not in valid_statuses:
            raise ValueError(
                f"invalid status '{status}'. Must be one of {valid_statuses}"
            )
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

    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search messages by content.

        Args:
            query: Search substring (case-insensitive)
            limit: Max messages to return

        Returns:
            List of matching message dicts

        Raises:
            ValueError: If query is empty
        """
        if not query or not query.strip():
            raise ValueError("search query must not be empty")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, created_at "
                "FROM messages WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query.lower()}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all messages in a thread.

        Args:
            thread_id: Thread ID

        Returns:
            List of message dicts in thread, ordered by creation time
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, created_at "
                "FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def stats(self) -> Dict[str, Any]:
        """Get bus statistics.

        Returns:
            Dict with message counts, agent counts, top senders, etc.
        """
        conn = self._connect()
        try:
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            thread_count = conn.execute(
                "SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL"
            ).fetchone()[0]
            broadcast_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient IS NULL"
            ).fetchone()[0]
            direct_count = msg_count - broadcast_count

            agents = conn.execute(
                "SELECT status, COUNT(*) FROM agents GROUP BY status"
            ).fetchall()
            agent_status = {row[0]: row[1] for row in agents}
            active_count = agent_status.get("active", 0)
            done_count = agent_status.get("done", 0)

            top_senders = conn.execute(
                "SELECT sender, COUNT(*) as count FROM messages "
                "GROUP BY sender ORDER BY count DESC LIMIT 5"
            ).fetchall()

            return {
                "messages": msg_count,
                "direct_messages": direct_count,
                "broadcasts": broadcast_count,
                "threads": thread_count,
                "agents_active": active_count,
                "agents_done": done_count,
                "top_senders": [
                    {"agent": row[0], "count": row[1]} for row in top_senders
                ],
            }
        finally:
            conn.close()


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
    print("  client.search(query, limit=50)")
    print("  client.thread(thread_id)")
    print("  client.stats()")
