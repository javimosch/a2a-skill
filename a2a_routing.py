#!/usr/bin/env python3
"""
a2a Message Routing — Smart message distribution and rule-based delivery (v1.3).

Enable agents to define routing rules for automatic message filtering,
forwarding, and delivery based on sender, content, priority, and thread.
"""

import sqlite3
import json
import re
import time
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from enum import Enum

from a2a_client import A2AClient


class RoutingAction(Enum):
    """Routing actions for matched messages."""

    DELIVER = "deliver"  # Deliver to this agent
    FORWARD = "forward"  # Forward to another agent
    DISCARD = "discard"  # Discard (delete)
    QUEUE = "queue"  # Queue for later processing
    ESCALATE = "escalate"  # Forward to escalation handler


class RoutingRule:
    """Configuration for a routing rule."""

    def __init__(
        self,
        name: str,
        action: RoutingAction,
        match_sender: Optional[str] = None,
        match_content: Optional[str] = None,
        match_priority: Optional[int] = None,
        match_thread: Optional[str] = None,
        forward_to: Optional[str] = None,
        enabled: bool = True,
    ):
        """Initialize routing rule.

        Args:
            name: Rule name
            action: Action when rule matches
            match_sender: Sender pattern (glob or regex)
            match_content: Content pattern (substring or regex)
            match_priority: Minimum priority level
            match_thread: Thread ID to match
            forward_to: Destination for FORWARD action
            enabled: Whether rule is active
        """
        self.name = name
        self.action = action
        self.match_sender = match_sender
        self.match_content = match_content
        self.match_priority = match_priority
        self.match_thread = match_thread
        self.forward_to = forward_to
        self.enabled = enabled
        self.created_at = time.time()

    def matches(self, message: Dict[str, Any]) -> bool:
        """Check if message matches rule criteria.

        Args:
            message: Message dict with sender, body, priority, thread_id

        Returns:
            True if message matches rule
        """
        if not self.enabled:
            return False

        # Check sender
        if self.match_sender:
            if not self._matches_pattern(message.get("sender", ""), self.match_sender):
                return False

        # Check content
        if self.match_content:
            if not self._matches_pattern(message.get("body", ""), self.match_content):
                return False

        # Check priority
        if self.match_priority is not None:
            msg_priority = message.get("priority", 2)
            if msg_priority < self.match_priority:
                return False

        # Check thread
        if self.match_thread:
            if message.get("thread_id") != self.match_thread:
                return False

        return True

    @staticmethod
    def _matches_pattern(text: str, pattern: str) -> bool:
        """Match text against pattern (substring or regex).

        Args:
            text: Text to match
            pattern: Pattern (substring or regex)

        Returns:
            True if pattern matches
        """
        # Try substring match first (case-insensitive)
        if pattern.lower() in text.lower():
            return True

        # Try regex match
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            pass

        return False


class RoutingClient(A2AClient):
    """Client with message routing capabilities."""

    def __init__(self, project: str, agent_id: str):
        """Initialize routing client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        super().__init__(project, agent_id)
        self.rules: List[RoutingRule] = []

    def init_routing_table(self) -> bool:
        """Initialize routing rules table.

        Returns:
            True if successful, False on error
        """
        conn = self._connect()
        try:
            conn.execute(
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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_routing_agent ON routing_rules(agent_id)"
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing routing: {e}")
            return False
        finally:
            conn.close()

    def add_rule(self, rule: RoutingRule) -> bool:
        """Add a routing rule.

        Args:
            rule: RoutingRule to add

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO routing_rules
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
            conn.commit()
            self.rules.append(rule)
            return True
        except Exception as e:
            print(f"Error adding rule: {e}")
            return False
        finally:
            conn.close()

    def get_rules(self) -> List[RoutingRule]:
        """Get all rules for this agent.

        Returns:
            List of RoutingRule objects
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
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
            for row in cursor.fetchall():
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
            conn.close()

    def disable_rule(self, rule_name: str) -> bool:
        """Disable a rule by name.

        Args:
            rule_name: Name of rule to disable

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE routing_rules
                SET enabled = 0
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error disabling rule: {e}")
            return False
        finally:
            conn.close()

    def enable_rule(self, rule_name: str) -> bool:
        """Enable a rule by name.

        Args:
            rule_name: Name of rule to enable

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE routing_rules
                SET enabled = 1
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error enabling rule: {e}")
            return False
        finally:
            conn.close()

    def delete_rule(self, rule_name: str) -> bool:
        """Delete a rule by name.

        Args:
            rule_name: Name of rule to delete

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                DELETE FROM routing_rules
                WHERE agent_id = ? AND rule_name = ?
            """,
                (self.agent_id, rule_name),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting rule: {e}")
            return False
        finally:
            conn.close()

    def recv_with_routing(
        self,
        wait: float = 0,
        unread_only: bool = True,
        include_self: bool = False,
        limit: int = 0,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Receive messages and route them according to rules.

        Args:
            wait: Block up to N seconds for messages
            unread_only: Only return unread messages
            include_self: Include messages sent by this agent
            limit: Max messages to return per category

        Returns:
            Dict with keys by action: 'deliver', 'forward', 'discard', 'queue', 'escalate'
        """
        # Get rules for this agent
        self.get_rules()

        # Get all messages
        messages = super().recv(
            wait=wait, unread_only=unread_only, include_self=include_self, limit=0
        )

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

        # Apply limits if specified
        if limit:
            for key in routed:
                routed[key] = routed[key][:limit]

        return routed

    def apply_routing(self, routed: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Apply routing decisions (forward, discard, etc).

        Args:
            routed: Result from recv_with_routing()

        Returns:
            True if successful
        """
        conn = self._connect()
        try:
            # Handle forwards
            for item in routed.get("forward", []):
                msg = item["message"]
                forward_to = item.get("forward_to")
                if forward_to:
                    # Forward original message
                    conn.execute(
                        "INSERT INTO messages(sender, recipient, body, priority, thread_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            self.agent_id,
                            forward_to,
                            f"[Forwarded] {msg['body']}",
                            msg.get("priority", 2),
                            msg.get("thread_id"),
                            time.time(),
                        ),
                    )

            # Handle discards
            for item in routed.get("discard", []):
                msg = item["message"]
                # Mark as read to hide
                conn.execute(
                    "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) "
                    "VALUES (?, ?, ?)",
                    (self.agent_id, msg["id"], time.time()),
                )

            conn.commit()
            return True
        except Exception as e:
            print(f"Error applying routing: {e}")
            return False
        finally:
            conn.close()

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics.

        Returns:
            Dict with rule counts and status
        """
        conn = self._connect()
        try:
            # Count rules
            cursor = conn.execute(
                "SELECT COUNT(*) FROM routing_rules WHERE agent_id = ?",
                (self.agent_id,),
            )
            total_rules = cursor.fetchone()[0]

            # Count enabled rules
            cursor = conn.execute(
                "SELECT COUNT(*) FROM routing_rules WHERE agent_id = ? AND enabled = 1",
                (self.agent_id,),
            )
            enabled_rules = cursor.fetchone()[0]

            # Count by action
            cursor = conn.execute(
                """
                SELECT action, COUNT(*) as count
                FROM routing_rules
                WHERE agent_id = ?
                GROUP BY action
            """,
                (self.agent_id,),
            )
            by_action = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "total_rules": total_rules,
                "enabled_rules": enabled_rules,
                "disabled_rules": total_rules - enabled_rules,
                "by_action": by_action,
            }
        finally:
            conn.close()


class SmartRouter:
    """Advanced routing with custom matchers and conditional logic."""

    def __init__(self, client: RoutingClient):
        """Initialize smart router.

        Args:
            client: RoutingClient instance
        """
        self.client = client
        self.custom_matchers: List[Callable[[Dict], bool]] = []
        self.handler_map: Dict[str, Callable[[Dict], None]] = {}

    def add_custom_matcher(
        self, matcher: Callable[[Dict], bool], handler: Callable[[Dict], None]
    ) -> "SmartRouter":
        """Add custom matcher with handler.

        Args:
            matcher: Function returning True if message matches
            handler: Function to handle matched message

        Returns:
            Self for chaining
        """
        self.custom_matchers.append((matcher, handler))
        return self

    def add_handler(self, action: str, handler: Callable[[Dict], None]) -> "SmartRouter":
        """Add handler for routing action.

        Args:
            action: Action name (deliver, forward, discard, etc)
            handler: Handler function

        Returns:
            Self for chaining
        """
        self.handler_map[action] = handler
        return self

    def route_message(self, message: Dict[str, Any]) -> bool:
        """Route single message with custom logic.

        Args:
            message: Message to route

        Returns:
            True if handled
        """
        # Try custom matchers first
        for matcher, handler in self.custom_matchers:
            if matcher(message):
                handler(message)
                return True

        # Fall back to rules
        self.client.get_rules()
        for rule in self.client.rules:
            if rule.matches(message):
                handler = self.handler_map.get(rule.action.value)
                if handler:
                    handler(message)
                return True

        return False

    def route_batch(self, messages: List[Dict[str, Any]]) -> Dict[str, int]:
        """Route batch of messages.

        Args:
            messages: List of messages to route

        Returns:
            Dict with counts by action
        """
        stats = {
            "deliver": 0,
            "forward": 0,
            "discard": 0,
            "queue": 0,
            "escalate": 0,
            "unhandled": 0,
        }

        for msg in messages:
            if self.route_message(msg):
                # Count the action taken (would need to track in handlers)
                pass
            else:
                stats["unhandled"] += 1

        return stats
