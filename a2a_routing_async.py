#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Async Message Routing — High-performance rule-based distribution (v1.3).

Non-blocking async version using aiosqlite for concurrent routing operations.
Full API parity with a2a_routing.RoutingClient.
"""

import asyncio
import time
from typing import List, Dict, Any
from pathlib import Path

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

from a2a_common import _validate_project_name, _validate_agent_id
from a2a_routing import RoutingAction, RoutingRule


class RoutingClientAsync:
    """Async client with message routing capabilities."""

    def __init__(self, project: str, agent_id: str):
        """Initialize async routing client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        if not HAS_AIOSQLITE:
            raise ImportError(
                "aiosqlite library required: pip install aiosqlite"
            )

        if not project or not project.strip():
            raise ValueError("project must not be empty")
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        _validate_project_name(project)
        _validate_agent_id(agent_id, "agent_id")

        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"
        self.rules: List[RoutingRule] = []

    async def _connect(self) -> "aiosqlite.Connection":
        """Connect to database asynchronously."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        return conn

    async def _cleanup_expired(self, conn: "aiosqlite.Connection") -> int:
        """Delete messages past their TTL. Return count deleted."""
        cursor = await conn.execute(
            "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
            (time.time(),),
        )
        return cursor.rowcount

    async def init_routing_table(self) -> bool:
        """Initialize routing rules table (async).

        Returns:
            True if successful, False on error
        """
        conn = await self._connect()
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS routing_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    match_sender TEXT,
                    match_content TEXT,
                    match_priority INTEGER,
                    match_thread TEXT,
                    forward_to TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    created_at REAL NOT NULL,
                    UNIQUE(agent_id, rule_name)
                )
            """
            )

            # Create index for rule lookup
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_routing_agent ON routing_rules(agent_id)"
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing routing: {e}")
            return False
        finally:
            await conn.close()

    async def add_rule(self, rule: RoutingRule) -> bool:
        """Add a routing rule (async).

        Args:
            rule: RoutingRule to add

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            await conn.execute(
                """
                INSERT OR IGNORE INTO routing_rules
                (agent_id, rule_name, action, match_sender, match_content,
                 match_priority, match_thread, forward_to, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.agent_id,
                    rule.name,
                    rule.action.value,
                    rule.match_sender,
                    rule.match_content,
                    rule.match_priority,
                    rule.match_thread,
                    rule.forward_to,
                    rule.enabled,
                    rule.created_at,
                ),
            )
            await conn.execute(
                """
                UPDATE routing_rules SET action=?, match_sender=?, match_content=?,
                 match_priority=?, match_thread=?, forward_to=?, enabled=?
                WHERE agent_id=? AND rule_name=?
            """,
                (
                    rule.action.value,
                    rule.match_sender,
                    rule.match_content,
                    rule.match_priority,
                    rule.match_thread,
                    rule.forward_to,
                    rule.enabled,
                    self.agent_id,
                    rule.name,
                ),
            )
            await conn.commit()
            for i, r in enumerate(self.rules):
                if r.name == rule.name:
                    self.rules[i] = rule
                    break
            else:
                self.rules.append(rule)
            return True
        except Exception as e:
            print(f"Error adding rule: {e}")
            return False
        finally:
            await conn.close()

    async def get_rules(self) -> List[RoutingRule]:
        """Get all rules for this agent (async).

        Returns:
            List of RoutingRule objects
        """
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                """
                SELECT rule_name, action, match_sender, match_content,
                       match_priority, match_thread, forward_to, enabled, created_at
                FROM routing_rules
                WHERE agent_id = ?
                ORDER BY created_at ASC
            """,
                (self.agent_id,),
            )

            rules = []
            async for row in cursor:
                rule = RoutingRule(
                    name=row[0],
                    action=RoutingAction(row[1]),
                    match_sender=row[2],
                    match_content=row[3],
                    match_priority=row[4],
                    match_thread=row[5],
                    forward_to=row[6],
                    enabled=bool(row[7]),
                )
                rule.created_at = row[8]
                rules.append(rule)

            self.rules = rules
            return rules
        finally:
            await conn.close()

    async def disable_rule(self, rule_name: str) -> bool:
        """Disable a rule by name (async).

        Args:
            rule_name: Name of rule to disable

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            await conn.execute(
                """
                UPDATE routing_rules
                SET enabled = 0
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            await conn.commit()
            await self.get_rules()
            return True
        except Exception as e:
            print(f"Error disabling rule: {e}")
            return False
        finally:
            await conn.close()

    async def enable_rule(self, rule_name: str) -> bool:
        """Enable a rule by name (async).

        Args:
            rule_name: Name of rule to enable

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            await conn.execute(
                """
                UPDATE routing_rules
                SET enabled = 1
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            await conn.commit()
            await self.get_rules()
            return True
        except Exception as e:
            print(f"Error enabling rule: {e}")
            return False
        finally:
            await conn.close()

    async def delete_rule(self, rule_name: str) -> bool:
        """Delete a rule by name (async).

        Args:
            rule_name: Name of rule to delete

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            await conn.execute(
                """
                DELETE FROM routing_rules
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting rule: {e}")
            return False
        finally:
            await conn.close()

    async def recv_with_routing(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Receive messages and route them according to rules (async).

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return per category

        Returns:
            Dict with keys by action: 'deliver', 'forward', 'discard', 'queue', 'escalate'
        """
        # Get rules for this agent
        await self.get_rules()

        # Get all messages
        deadline = time.time() + wait if wait else None
        poll_interval = 0.1
        messages = []

        conn = await self._connect()
        try:
            while True:
                if await self._cleanup_expired(conn):
                    await conn.commit()
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

                cursor = await conn.execute(base, params)
                messages = []
                async for row in cursor:
                    messages.append(dict(row))

                if messages or not wait or (deadline and time.time() >= deadline):
                    break

                await asyncio.sleep(poll_interval)

            if messages:
                ts = time.time()
                for msg in messages:
                    await conn.execute(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?, ?, ?)",
                        (self.agent_id, msg["id"], ts),
                    )
                await conn.commit()
        finally:
            await conn.close()

        # Route messages
        routed = {
            "deliver": [],
            "forward": [],
            "discard": [],
            "queue": [],
            "escalate": [],
        }

        for msg in messages:
            # Find first matching rule
            matched = False
            for rule in self.rules:
                if rule.matches(msg):
                    action_key = rule.action.value
                    routed[action_key].append(
                        {
                            "message": msg,
                            "rule": rule.name,
                            "forward_to": rule.forward_to,
                        }
                    )
                    matched = True
                    break

            # If no rule matches, default to deliver
            if not matched:
                routed["deliver"].append({"message": msg, "rule": None})

        # Apply limits per-category post-routing (match sync behavior)
        if limit:
            for key in routed:
                routed[key] = routed[key][:limit]

        return routed

    async def apply_routing(self, routed: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Apply routing decisions (forward, discard, etc) (async).

        Args:
            routed: Result from recv_with_routing()

        Returns:
            True if successful
        """
        conn = await self._connect()
        try:
            # Handle forwards
            for item in routed.get("forward", []):
                msg = item["message"]
                forward_to = item.get("forward_to")
                if forward_to:
                    # Forward original message
                    await conn.execute(
                        "INSERT INTO messages(sender, recipient, body, priority, thread_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            self.agent_id,
                            forward_to,
                            f"[Forwarded] {msg.get('body') or ''}",
                            msg.get("priority", 2),
                            msg.get("thread_id"),
                            time.time(),
                        ),
                    )

            # Mark all processed messages as read to prevent re-processing
            for category in ("deliver", "forward", "discard", "queue", "escalate"):
                for item in routed.get(category, []):
                    msg = item["message"]
                    await conn.execute(
                        "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) "
                        "VALUES (?, ?, ?)",
                        (self.agent_id, msg["id"], time.time()),
                    )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Error applying routing: {e}")
            return False
        finally:
            await conn.close()

    async def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics (async).

        Returns:
            Dict with rule counts and status
        """
        conn = await self._connect()
        try:
            # Count rules
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM routing_rules WHERE agent_id = ?",
                (self.agent_id,),
            )
            row = await cursor.fetchone()
            total_rules = row[0] if row else 0

            # Count enabled rules
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM routing_rules WHERE agent_id = ? AND enabled = 1",
                (self.agent_id,),
            )
            row = await cursor.fetchone()
            enabled_rules = row[0] if row else 0

            # Count by action
            cursor = await conn.execute(
                """
                SELECT action, COUNT(*) as count
                FROM routing_rules
                WHERE agent_id = ?
                GROUP BY action
            """,
                (self.agent_id,),
            )
            by_action = {}
            async for row in cursor:
                by_action[row[0]] = row[1]

            return {
                "total_rules": total_rules,
                "enabled_rules": enabled_rules,
                "disabled_rules": total_rules - enabled_rules,
                "by_action": by_action,
            }
        finally:
            await conn.close()


async def run_agents(agents: List) -> List:
    """Run multiple async routing agents concurrently.

    Args:
        agents: List of coroutines to run

    Returns:
        List of results
    """
    return await asyncio.gather(*agents)
