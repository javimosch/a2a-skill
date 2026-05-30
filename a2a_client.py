#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a2a Client Library — Python API for a2a peer messaging.

Provides object-oriented access to a2a messaging without shell invocation.
"""

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from a2a_common import MAX_ID_LENGTH, MAX_ROLE_LENGTH, MAX_THREAD_ID_LENGTH, MAX_BODY_LENGTH
from a2a_common import _validate_project_name, _validate_agent_id


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
        _validate_project_name(project)
        _validate_agent_id(agent_id, "agent_id")
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
        priority: int = 3,
        require_ack: bool = False,
    ) -> int:
        """Send a message.

        Args:
            to: Recipient agent ID, or "all" for broadcast
            message: Message body
            ttl_seconds: Optional time-to-live in seconds
            thread_id: Optional thread ID to group related messages
            priority: Message priority 1-4 (1=URGENT, 2=HIGH, 3=NORMAL, 4=LOW)
            require_ack: If True, recipient must acknowledge receipt

        Returns:
            Message ID

        Raises:
            ValueError: If recipient is empty or priority is invalid
        """
        conn = self._connect()
        try:
            if not to or not to.strip():
                raise ValueError("recipient must not be empty")
            if priority not in (1, 2, 3, 4):
                raise ValueError("priority must be 1 (URGENT), 2 (HIGH), 3 (NORMAL), or 4 (LOW)")
            cur = conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (self.agent_id,))
            if cur.fetchone()[0] == 0:
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
                cur = conn.execute("SELECT COUNT(1) FROM agents WHERE id=?", (recipient,))
                if cur.fetchone()[0] == 0:
                    raise ValueError(f"unknown recipient '{recipient}' — register them first")
            cur = conn.execute(
                "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, priority, requires_ack, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.agent_id, recipient, message, thread_id, ttl_seconds, priority, 1 if require_ack else 0, time.time()),
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
        pid: int | None = None,
        upsert: bool = True,
    ) -> bool:
        """Register this agent on the bus.

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
                    "UPDATE agents SET role=COALESCE(NULLIF(?,''),role), prompt=COALESCE(NULLIF(?,''),prompt), "
                    "cli=COALESCE(NULLIF(?,''),cli), pid=COALESCE(?,pid), status='active', last_seen=? "
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
        priority_min: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return (0 = unlimited)
            priority_min: Min priority (1=URGENT, 4=LOW; returns >= this level)

        Returns:
            List of message dicts

        Raises:
            ValueError: If wait is negative or priority_min is invalid

        """
        if wait < 0:
            raise ValueError("wait must be a non-negative number of seconds")
        if not math.isfinite(wait):
            raise ValueError("wait must be a finite number")
        if limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if priority_min is not None and (priority_min < 1 or priority_min > 4):
            raise ValueError("priority_min must be 1-4")
        conn = self._connect()
        try:
            deadline = time.time() + wait if wait else None
            poll_interval = 0.1

            while True:
                self._cleanup_expired(conn)
                conn.commit()
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

                if priority_min is not None:
                    base += "AND m.priority <= ? "
                    params.append(priority_min)

                base += "ORDER BY m.priority ASC, m.created_at ASC"
                if limit:
                    base += " LIMIT ?"
                    params.append(limit)

                rows = conn.execute(base, params).fetchall()

                if rows:
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
            conn.commit()
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
                "FROM messages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def list(self) -> List[Dict[str, Any]]:
        """Get list of registered agents (alias for list_peers).

        Returns:
            List of agent dicts with id, role, status, etc.
        """
        return self.list_peers()

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

    def touch(self) -> None:
        """Update this agent's last_seen timestamp to the current time.

        Useful for heartbeat / keep-alive signals so other agents know this
        agent is still active.
        """
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE agents SET last_seen=? WHERE id=?",
                (time.time(), self.agent_id),
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

    def status(self, new_status: Optional[str] = None) -> Optional[str]:
        """Get or set this agent's status.

        Args:
            new_status: If provided, set status; if None, return current status

        Returns:
            Status string if getting, None if setting
        """
        if new_status is not None:
            self.set_status(new_status)
            return None
        return self.get_status()

    def wait(
        self, count: int = 1, timeout: float = 60
    ) -> bool:
        """Block until N unread messages or timeout (alias for wait_for_messages).

        Args:
            count: Number of unread messages to wait for (must be positive)
            timeout: Max seconds to wait (must be non-negative)

        Returns:
            True if got N messages, False on timeout
        """
        return self.wait_for_messages(count, timeout)

    def wait_for_messages(
        self, count: int = 1, timeout: float = 60
    ) -> bool:
        """Block until N unread messages or timeout.

        Accumulates messages across polls so count > 1 works even when
        messages arrive one at a time. Messages are marked as read as
        they arrive.

        Args:
            count: Number of unread messages to wait for (must be positive)
            timeout: Max seconds to wait (must be non-negative)

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
            msgs = self.recv(unread_only=True, wait=0)
            seen.extend(msgs)
            if len(seen) >= count:
                return True
            if not msgs:
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
            ValueError: If query is empty or limit is not positive
        """
        if not query or not query.strip():
            raise ValueError("search query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
                "FROM messages WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query.lower()}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all messages in a thread.

        Args:
            thread_id: Thread ID (must not be empty)

        Returns:
            List of message dicts in thread, ordered by creation time

        Raises:
            ValueError: If thread_id is empty or whitespace-only
        """
        if not thread_id or not thread_id.strip():
            raise ValueError("thread_id must not be empty")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
                "FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def stats(self) -> Dict[str, Any]:
        """Get bus statistics.

        Returns:
            Dict with message counts, agent counts, priority distribution, task stats, etc.
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

            priority_dist = conn.execute(
                "SELECT priority, COUNT(*) FROM messages WHERE priority IS NOT NULL GROUP BY priority"
            ).fetchall()
            priority_labels = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}
            priority_stats = {}
            for row in priority_dist:
                label = priority_labels.get(row[0], f"P{row[0]}")
                priority_stats[label] = row[1]

            ack_required = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE requires_ack = 1"
            ).fetchone()[0]
            acks_sent = conn.execute(
                "SELECT COUNT(*) FROM acknowledgments"
            ).fetchone()[0]

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

            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            task_statuses = conn.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            ).fetchall()
            task_status_dict = {row[0]: row[1] for row in task_statuses}

            return {
                "messages": msg_count,
                "direct_messages": direct_count,
                "broadcasts": broadcast_count,
                "threads": thread_count,
                "priority_distribution": priority_stats,
                "acks_required": ack_required,
                "acks_sent": acks_sent,
                "agents_active": active_count,
                "agents_done": done_count,
                "tasks_total": task_count,
                "tasks_by_status": task_status_dict,
                "top_senders": [
                    {"agent": row[0], "count": row[1]} for row in top_senders
                ],
            }
        finally:
            conn.close()

    def ack(self, message_id: int) -> bool:
        """Acknowledge receipt of a message.

        Args:
            message_id: Message ID to acknowledge

        Returns:
            True on success

        Raises:
            ValueError: If message_id is not positive or message not found
        """
        if message_id <= 0:
            raise ValueError("message_id must be a positive integer")
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM messages WHERE id=?", (message_id,)).fetchone()
            if not row:
                raise ValueError(f"message #{message_id} not found")
            conn.execute(
                "INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?,?,?)",
                (message_id, self.agent_id, time.time()),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def pending_acks(self) -> List[Dict[str, Any]]:
        """Get messages that requested acknowledgment but haven't been acked.

        Returns:
            List of message dicts requiring acknowledgment
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.priority, m.requires_ack, m.created_at "
                "FROM messages m "
                "WHERE m.requires_ack = 1 AND m.recipient = ? "
                "AND NOT EXISTS (SELECT 1 FROM acknowledgments a WHERE a.message_id = m.id AND a.agent_id = ?) "
                "ORDER BY m.created_at ASC",
                (self.agent_id, self.agent_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def heartbeat(self, status: str = "active") -> None:
        """Send a heartbeat to keep agent registration alive.

        Args:
            status: Status update ('active', 'working', 'idle', 'error')

        Raises:
            ValueError: If status is invalid
        """
        valid = ("active", "working", "idle", "error")
        if status not in valid:
            raise ValueError(f"status must be one of {valid}")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE agents SET last_seen=?, status=? WHERE id=?",
                (time.time(), status, self.agent_id),
            )
            conn.commit()
        finally:
            conn.close()

    def heartbeat_check(self, grace: float = 120) -> List[Dict[str, Any]]:
        """Check for agents that missed too many heartbeats.

        Args:
            grace: Seconds since last_seen to consider stale (default: 120)

        Returns:
            List of stale agent dicts

        Raises:
            ValueError: If grace is not positive
        """
        if grace <= 0:
            raise ValueError("grace must be a positive number of seconds")
        conn = self._connect()
        try:
            threshold = time.time() - grace
            rows = conn.execute(
                "SELECT id, status, last_seen FROM agents WHERE last_seen < ? ORDER BY last_seen",
                (threshold,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_task(
        self,
        title: str,
        description: str = "",
        assigned_to: str = "",
        priority: int = 3,
        depends_on: Optional[List[int]] = None,
    ) -> int:
        """Create a new task in the shared task queue.

        Args:
            title: Task title (required)
            description: Optional task description
            assigned_to: Optional agent to assign to
            priority: Task priority 1-4 (1=highest)
            depends_on: Optional list of task IDs this task depends on

        Returns:
            Task ID

        Raises:
            ValueError: If title is empty or priority is invalid
        """
        if not title or not title.strip():
            raise ValueError("task title must not be empty")
        if priority not in (1, 2, 3, 4):
            raise ValueError("priority must be 1-4")
        conn = self._connect()
        try:
            ts = time.time()
            deps = json.dumps(depends_on) if depends_on else None
            cur = conn.execute(
                "INSERT INTO tasks(title, description, assigned_to, status, priority, dependencies, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (title, description, assigned_to, "planned", priority, deps, ts, ts),
            )
            conn.commit()
            tid = cur.lastrowid
            if depends_on:
                for dep_id in depends_on:
                    conn.execute(
                        "INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES (?,?)",
                        (tid, dep_id),
                    )
                conn.commit()
            return tid
        finally:
            conn.close()

    def list_tasks(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters.

        Args:
            status: Filter by status ('planned', 'in_progress', 'review_pending', 'approved', 'done', 'blocked')
            assigned_to: Filter by assigned agent

        Returns:
            List of task dicts
        """
        valid_statuses = {"planned", "in_progress", "review_pending", "approved", "done", "blocked"}
        conn = self._connect()
        try:
            query = "SELECT * FROM tasks"
            params = []
            conditions = []
            if status:
                if status not in valid_statuses:
                    raise ValueError(f"invalid status '{status}'")
                conditions.append("status = ?")
                params.append(status)
            if assigned_to:
                conditions.append("assigned_to = ?")
                params.append(assigned_to)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY priority ASC, created_at DESC"
            rows = conn.execute(query, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("dependencies") and isinstance(d["dependencies"], str):
                    try:
                        d["dependencies"] = json.loads(d["dependencies"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append(d)
            return result
        finally:
            conn.close()

    def update_task_status(self, task_id: int, new_status: str) -> None:
        """Update task status with state machine validation.

        Args:
            task_id: Task ID
            new_status: New status value

        Raises:
            ValueError: If task not found or transition is invalid
        """
        valid_statuses = {"planned", "in_progress", "review_pending", "approved", "done", "blocked"}
        transitions = {
            "planned": {"in_progress"},
            "in_progress": {"review_pending", "blocked", "done"},
            "review_pending": {"approved", "in_progress", "blocked"},
            "approved": {"done", "in_progress"},
            "done": set(),
            "blocked": {"in_progress"},
        }
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        if new_status not in valid_statuses:
            raise ValueError(f"invalid status '{new_status}'")
        conn = self._connect()
        try:
            row = conn.execute("SELECT id, status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError(f"task #{task_id} not found")
            current = row["status"]
            if new_status not in transitions.get(current, set()):
                allowed = transitions.get(current, set())
                if not allowed:
                    raise ValueError(f"cannot transition from '{current}' — terminal state")
                raise ValueError(f"invalid transition from '{current}' to '{new_status}'")
            ts = time.time()
            updates = {"status": new_status, "updated_at": ts}
            if new_status == "in_progress" and current != "in_progress":
                updates["claimed_at"] = ts
            if new_status == "done":
                updates["completed_at"] = ts
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", (*updates.values(), task_id))
            conn.commit()
        finally:
            conn.close()

    def claim_task(self, task_id: int) -> None:
        """Claim a task by assigning self and setting status to in_progress.

        Args:
            task_id: Task ID

        Raises:
            ValueError: If task not found, done, or already assigned to another agent
        """
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = self._connect()
        try:
            row = conn.execute("SELECT id, status, assigned_to FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError(f"task #{task_id} not found")
            if row["status"] == "done":
                raise ValueError(f"task #{task_id} is already done")
            if row["assigned_to"] and row["assigned_to"] != self.agent_id:
                raise ValueError(f"task #{task_id} already assigned to '{row['assigned_to']}'")
            ts = time.time()
            self.update_task_status(task_id, "in_progress")
            conn.execute(
                "UPDATE tasks SET assigned_to=?, claimed_at=? WHERE id=?",
                (self.agent_id, ts, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_task(self, task_id: int, result: str = "") -> None:
        """Complete a task.

        Args:
            task_id: Task ID
            result: Optional result description

        Raises:
            ValueError: If task not found or cannot transition to done
        """
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        self.update_task_status(task_id, "done")
        conn = self._connect()
        try:
            ts = time.time()
            conn.execute(
                "UPDATE tasks SET result=?, completed_at=?, updated_at=? WHERE id=?",
                (result, ts, ts, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def init_project(self) -> None:
        """Initialize the project database, creating tables if they don't exist.

        Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
        """
        conn = self._connect()
        try:
            conn.executescript("""
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
                    priority    INTEGER DEFAULT 3,
                    requires_ack INTEGER DEFAULT 0,
                    created_at  REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reads (
                    agent_id    TEXT NOT NULL,
                    message_id  INTEGER NOT NULL,
                    read_at     REAL NOT NULL,
                    PRIMARY KEY (agent_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS acknowledgments (
                    message_id  INTEGER NOT NULL,
                    agent_id    TEXT NOT NULL,
                    acked_at    REAL NOT NULL,
                    PRIMARY KEY (message_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    description TEXT,
                    assigned_to TEXT,
                    status      TEXT NOT NULL DEFAULT 'planned',
                    priority    INTEGER DEFAULT 3,
                    dependencies TEXT,
                    result      TEXT,
                    claimed_at  REAL,
                    completed_at REAL,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_deps (
                    task_id     INTEGER NOT NULL,
                    depends_on  INTEGER NOT NULL,
                    PRIMARY KEY (task_id, depends_on)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
                CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_task_deps_task ON task_deps(task_id);
            """)
            conn.commit()
        finally:
            conn.close()

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

    def clear(self) -> None:
        """Delete the project database and all WAL-related files.

        Warning: This permanently deletes all messages and agent registrations.
        """
        from pathlib import Path as _Path
        for suffix in ("", "-wal", "-shm"):
            p = _Path(str(self.db_path) + suffix)
            if p.exists():
                p.unlink()

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
    print("  client.init_project()")
    print("  client.project_info()")
    print("  client.clear()")
    print("  client.send(to, message, ttl_seconds=None, thread_id=None, priority=3, require_ack=False)")
    print("  client.recv(wait=0, unread_only=True, include_self=False, limit=0, priority_min=None)")
    print("  client.peek(limit=20)")
    print("  client.list_peers()")
    print("  client.set_status(status)")
    print("  client.get_status(agent_id=None)")
    print("  client.wait_for_messages(count=1, timeout=60)")
    print("  client.search(query, limit=50)")
    print("  client.thread(thread_id)")
    print("  client.stats()")
    print("  client.ack(message_id)")
    print("  client.pending_acks()")
    print("  client.heartbeat(status='active')")
    print("  client.heartbeat_check(grace=120)")
    print("  client.create_task(title, description='', assigned_to='', priority=3, depends_on=None)")
    print("  client.list_tasks(status=None, assigned_to=None)")
    print("  client.update_task_status(task_id, new_status)")
    print("  client.claim_task(task_id)")
    print("  client.complete_task(task_id, result='')")
