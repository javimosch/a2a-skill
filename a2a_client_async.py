#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Async Client Library — Asyncio-based API for high-performance a2a messaging.

Provides async/await interface for concurrent agent patterns.
"""

import aiosqlite
import asyncio
import json
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
        conn = await self._connect()
        if not to or not to.strip():
            raise ValueError("recipient must not be empty")
        if priority not in (1, 2, 3, 4):
            raise ValueError("priority must be 1 (URGENT), 2 (HIGH), 3 (NORMAL), or 4 (LOW)")
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
            "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, priority, requires_ack, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.agent_id, recipient, message, thread_id, ttl_seconds, priority, 1 if require_ack else 0, time.time()),
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
        priority_min: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Receive messages.

        Args:
            wait: Max seconds to wait for messages (supports fractional)
            unread_only: Only return unread messages
            include_self: Include messages from self
            limit: Max number of messages to return (0 = unlimited)
            priority_min: Min priority (1=URGENT, 4=LOW; returns >= this level)

        Returns:
            List of message dicts

        Raises:
            ValueError: If wait is negative or priority_min is invalid

        """
        conn = await self._connect()
        if wait < 0:
            raise ValueError("wait must be a non-negative number of seconds")
        if not math.isfinite(wait):
            raise ValueError("wait must be a finite number")
        if limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if priority_min is not None and (priority_min < 1 or priority_min > 4):
            raise ValueError("priority_min must be 1-4")
        deadline = time.time() + wait if wait > 0 else None

        while True:
            await self._cleanup_expired(conn)
            await conn.commit()
            query = (
                "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
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

            if priority_min is not None:
                query += " AND priority <= ?"
                params.append(priority_min)

            query += " ORDER BY priority ASC, created_at ASC"
            if limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            if rows:
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
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
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
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
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
            "SELECT id, sender, recipient, body, thread_id, priority, requires_ack, created_at "
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

    # ---- task methods (phase 2) ----

    def _validate_task_status(self, status: str) -> None:
        valid = {"planned", "in_progress", "review_pending", "approved", "done", "blocked"}
        if status not in valid:
            raise ValueError(f"invalid status '{status}'")

    def _validate_task_transition(self, current: str, next_status: str) -> None:
        transitions = {
            "planned": {"in_progress"},
            "in_progress": {"review_pending", "blocked", "done"},
            "review_pending": {"approved", "in_progress", "blocked"},
            "approved": {"done", "in_progress"},
            "done": set(),
            "blocked": {"in_progress"},
        }
        self._validate_task_status(current)
        self._validate_task_status(next_status)
        allowed = transitions.get(current, set())
        if next_status not in allowed:
            if not allowed:
                raise ValueError(f"cannot transition from '{current}' — terminal state")
            raise ValueError(f"invalid transition from '{current}' to '{next_status}'")

    async def create_task(
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
        """
        if not title or not title.strip():
            raise ValueError("task title must not be empty")
        if priority not in (1, 2, 3, 4):
            raise ValueError("priority must be 1-4")
        conn = await self._connect()
        try:
            ts = time.time()
            deps = json.dumps(depends_on) if depends_on else None
            cursor = await conn.execute(
                "INSERT INTO tasks(title, description, assigned_to, status, priority, dependencies, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (title, description, assigned_to, "planned", priority, deps, ts, ts),
            )
            await conn.commit()
            tid = cursor.lastrowid
            if depends_on:
                for dep_id in depends_on:
                    await conn.execute(
                        "INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES (?,?)",
                        (tid, dep_id),
                    )
                await conn.commit()
            return tid
        finally:
            await conn.close()

    async def list_tasks(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters."""
        conn = await self._connect()
        try:
            query = "SELECT * FROM tasks"
            params = []
            conditions = []
            if status:
                self._validate_task_status(status)
                conditions.append("status = ?")
                params.append(status)
            if assigned_to:
                conditions.append("assigned_to = ?")
                params.append(assigned_to)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY priority ASC, created_at DESC"
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
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
            await conn.close()

    async def update_task_status(self, task_id: int, new_status: str) -> None:
        """Update task status with state machine validation."""
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = await self._connect()
        try:
            cursor = await conn.execute("SELECT id, status FROM tasks WHERE id=?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"task #{task_id} not found")
            current = row["status"]
            self._validate_task_transition(current, new_status)
            ts = time.time()
            updates = {"status": new_status, "updated_at": ts}
            if new_status == "in_progress" and current != "in_progress":
                updates["claimed_at"] = ts
            if new_status == "done":
                updates["completed_at"] = ts
            set_clause = ", ".join(f"{k}=?" for k in updates)
            await conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id=?",
                (*updates.values(), task_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def claim_task(self, task_id: int) -> None:
        """Claim a task by assigning self and setting status to in_progress."""
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                "SELECT id, status, assigned_to FROM tasks WHERE id=?", (task_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"task #{task_id} not found")
            if row["status"] == "done":
                raise ValueError(f"task #{task_id} is already done")
            if row["assigned_to"] and row["assigned_to"] != self.agent_id:
                raise ValueError(f"task #{task_id} already assigned to '{row['assigned_to']}'")
            ts = time.time()
            await conn.execute(
                "UPDATE tasks SET status='in_progress', assigned_to=?, claimed_at=?, updated_at=? WHERE id=?",
                (self.agent_id, ts, ts, task_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def complete_task(self, task_id: int, result: str = "") -> None:
        """Complete a task."""
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = await self._connect()
        try:
            cursor = await conn.execute("SELECT id, status FROM tasks WHERE id=?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"task #{task_id} not found")
            ts = time.time()
            await conn.execute(
                "UPDATE tasks SET status='done', result=?, completed_at=?, updated_at=? WHERE id=?",
                (result, ts, ts, task_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def stats(self) -> Dict[str, Any]:
        """Get bus statistics.

        Returns:
            Stats dict with message/agent counts
        """
        conn = await self._connect()

        # Count messages
        cursor = await conn.execute("SELECT COUNT(*) as count FROM messages")
        messages = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM messages WHERE recipient IS NULL"
        )
        broadcasts = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT COUNT(DISTINCT thread_id) as count "
            "FROM messages WHERE thread_id IS NOT NULL"
        )
        threads = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT priority, COUNT(*) as count FROM messages WHERE priority IS NOT NULL GROUP BY priority"
        )
        priority_rows = await cursor.fetchall()
        priority_labels = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}
        priority_stats = {}
        for row in priority_rows:
            label = priority_labels.get(row["priority"], f"P{row['priority']}")
            priority_stats[label] = row["count"]

        cursor = await conn.execute("SELECT COUNT(*) as count FROM messages WHERE requires_ack = 1")
        ack_required = (await cursor.fetchone())["count"]

        cursor = await conn.execute("SELECT COUNT(*) as count FROM acknowledgments")
        acks_sent = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM agents WHERE status = 'active'"
        )
        agents_active = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM agents WHERE status = 'done'"
        )
        agents_done = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT sender, COUNT(*) as count FROM messages "
            "GROUP BY sender ORDER BY count DESC LIMIT 5"
        )
        top_senders = [
            {"agent": row["sender"], "count": row["count"]}
            for row in await cursor.fetchall()
        ]

        cursor = await conn.execute("SELECT COUNT(*) as count FROM tasks")
        task_count = (await cursor.fetchone())["count"]

        cursor = await conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        )
        task_statuses = await cursor.fetchall()
        task_status_dict = {row["status"]: row["count"] for row in task_statuses}

        return {
            "messages": messages,
            "direct_messages": messages - broadcasts,
            "broadcasts": broadcasts,
            "threads": threads,
            "priority_distribution": priority_stats,
            "acks_required": ack_required,
            "acks_sent": acks_sent,
            "agents_active": agents_active,
            "agents_done": agents_done,
            "tasks_total": task_count,
            "tasks_by_status": task_status_dict,
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

    async def ack(self, message_id: int) -> bool:
        """Acknowledge receipt of a message.

        Args:
            message_id: Message ID to acknowledge

        Returns:
            True on success
        """
        if message_id <= 0:
            raise ValueError("message_id must be a positive integer")
        conn = await self._connect()
        row = await (await conn.execute("SELECT id FROM messages WHERE id=?", (message_id,))).fetchone()
        if not row:
            raise ValueError(f"message #{message_id} not found")
        await conn.execute(
            "INSERT OR IGNORE INTO acknowledgments(message_id, agent_id, acked_at) VALUES (?,?,?)",
            (message_id, self.agent_id, time.time()),
        )
        await conn.commit()
        return True

    async def pending_acks(self) -> List[Dict[str, Any]]:
        """Get messages that requested acknowledgment but haven't been acked.

        Returns:
            List of message dicts requiring acknowledgment
        """
        conn = await self._connect()
        cursor = await conn.execute(
            "SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.priority, m.requires_ack, m.created_at "
            "FROM messages m "
            "WHERE m.requires_ack = 1 AND m.recipient = ? "
            "AND NOT EXISTS (SELECT 1 FROM acknowledgments a WHERE a.message_id = m.id AND a.agent_id = ?) "
            "ORDER BY m.created_at ASC",
            (self.agent_id, self.agent_id),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def heartbeat(self, status: str = "active") -> None:
        """Send a heartbeat to keep agent registration alive.

        Args:
            status: Status update ('active', 'working', 'idle', 'error')
        """
        valid = ("active", "working", "idle", "error")
        if status not in valid:
            raise ValueError(f"status must be one of {valid}")
        conn = await self._connect()
        await conn.execute(
            "UPDATE agents SET last_seen=?, status=? WHERE id=?",
            (time.time(), status, self.agent_id),
        )
        await conn.commit()

    async def heartbeat_check(self, grace: float = 120) -> List[Dict[str, Any]]:
        """Check for agents that missed too many heartbeats.

        Args:
            grace: Seconds since last_seen to consider stale (default: 120)

        Returns:
            List of stale agent dicts
        """
        if grace <= 0:
            raise ValueError("grace must be a positive number of seconds")
        conn = await self._connect()
        threshold = time.time() - grace
        cursor = await conn.execute(
            "SELECT id, status, last_seen FROM agents WHERE last_seen < ? ORDER BY last_seen",
            (threshold,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def create_task(
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
        """
        if not title or not title.strip():
            raise ValueError("task title must not be empty")
        if priority not in (1, 2, 3, 4):
            raise ValueError("priority must be 1-4")
        conn = await self._connect()
        ts = time.time()
        deps = json.dumps(depends_on) if depends_on else None
        cursor = await conn.execute(
            "INSERT INTO tasks(title, description, assigned_to, status, priority, dependencies, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (title, description, assigned_to, "planned", priority, deps, ts, ts),
        )
        tid = cursor.lastrowid
        if depends_on:
            for dep_id in depends_on:
                await conn.execute(
                    "INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES (?,?)",
                    (tid, dep_id),
                )
        await conn.commit()
        return tid

    async def list_tasks(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters.

        Args:
            status: Filter by status
            assigned_to: Filter by assigned agent

        Returns:
            List of task dicts
        """
        valid_statuses = {"planned", "in_progress", "review_pending", "approved", "done", "blocked"}
        conn = await self._connect()
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
        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
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

    async def update_task_status(self, task_id: int, new_status: str) -> None:
        """Update task status with state machine validation.

        Args:
            task_id: Task ID
            new_status: New status value
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
        conn = await self._connect()
        cursor = await conn.execute("SELECT id, status FROM tasks WHERE id=?", (task_id,))
        row = await cursor.fetchone()
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
        await conn.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", (*updates.values(), task_id))
        await conn.commit()

    async def claim_task(self, task_id: int) -> None:
        """Claim a task by assigning self and setting status to in_progress.

        Args:
            task_id: Task ID
        """
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = await self._connect()
        cursor = await conn.execute("SELECT id, status, assigned_to FROM tasks WHERE id=?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"task #{task_id} not found")
        if row["status"] == "done":
            raise ValueError(f"task #{task_id} is already done")
        if row["assigned_to"] and row["assigned_to"] != self.agent_id:
            raise ValueError(f"task #{task_id} already assigned to '{row['assigned_to']}'")
        ts = time.time()
        await self.update_task_status(task_id, "in_progress")
        await conn.execute(
            "UPDATE tasks SET assigned_to=?, claimed_at=? WHERE id=?",
            (self.agent_id, ts, task_id),
        )
        await conn.commit()

    async def complete_task(self, task_id: int, result: str = "") -> None:
        """Complete a task.

        Args:
            task_id: Task ID
            result: Optional result description
        """
        if task_id <= 0:
            raise ValueError("task_id must be a positive integer")
        conn = await self._connect()
        cursor = await conn.execute("SELECT id, status FROM tasks WHERE id=?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"task #{task_id} not found")
        ts = time.time()
        await conn.execute(
            "UPDATE tasks SET status='done', result=?, completed_at=?, updated_at=? WHERE id=?",
            (result, ts, ts, task_id),
        )
        await conn.commit()

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
