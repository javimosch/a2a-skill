#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for a2a_client.py"""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from a2a_client import A2AClient


class TestA2AClient(unittest.TestCase):
    """Test a2a Python client."""

    @classmethod
    def setUpClass(cls):
        """Set up test project directory."""
        cls.test_home = tempfile.mkdtemp()
        cls.original_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.test_home

    @classmethod
    def tearDownClass(cls):
        """Restore original HOME."""
        if cls.original_home:
            os.environ["HOME"] = cls.original_home

    def setUp(self):
        """Initialize test project."""
        self.project = f"a2a-client-test-{id(self)}"
        self.project_dir = Path.home() / ".a2a" / self.project
        self.project_dir.mkdir(parents=True, exist_ok=True)

        # Create fresh database with schema
        db_path = self.project_dir / "database.db"
        conn = sqlite3.connect(str(db_path))
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
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reads (
                agent_id    TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                read_at     REAL NOT NULL,
                PRIMARY KEY (agent_id, message_id)
            );
        """)

        # Register test agents
        ts = time.time()
        conn.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) VALUES (?,?,?,?,?)",
            ("alice", "tester", "active", ts, ts),
        )
        conn.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) VALUES (?,?,?,?,?)",
            ("bob", "tester", "active", ts, ts),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test project."""
        import shutil
        db_path = self.project_dir / "database.db"
        if db_path.exists():
            db_path.unlink()
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)

    def test_send_direct(self):
        """Test sending a direct message."""
        alice = A2AClient(self.project, "alice")
        msg_id = alice.send("bob", "Hello Bob")

        self.assertIsInstance(msg_id, int)
        self.assertGreater(msg_id, 0)

    def test_send_broadcast(self):
        """Test broadcast message."""
        alice = A2AClient(self.project, "alice")
        msg_id = alice.send("all", "Team message")

        self.assertIsInstance(msg_id, int)
        self.assertGreater(msg_id, 0)

    def test_send_with_ttl(self):
        """Test sending with TTL."""
        alice = A2AClient(self.project, "alice")
        msg_id = alice.send("bob", "Short-lived msg", ttl_seconds=3600)

        self.assertGreater(msg_id, 0)

    def test_recv_direct(self):
        """Test receiving a direct message."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Hello from Alice")

        messages = bob.recv(wait=1)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["sender"], "alice")
        self.assertEqual(messages[0]["body"], "Hello from Alice")

    def test_recv_broadcast(self):
        """Test receiving broadcast."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("all", "Broadcast message")

        messages = bob.recv(wait=1)
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0]["recipient"])

    def test_recv_unread_only(self):
        """Test that recv marks messages as read."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Message 1")
        alice.send("bob", "Message 2")

        # First recv gets both
        messages1 = bob.recv(wait=1)
        self.assertEqual(len(messages1), 2)

        # Second recv gets nothing (already read)
        messages2 = bob.recv(wait=0)
        self.assertEqual(len(messages2), 0)

    def test_recv_with_include_self(self):
        """Test include_self parameter."""
        alice = A2AClient(self.project, "alice")

        alice.send("bob", "To Bob")
        alice.send("alice", "To Self")  # Self message

        # Without include_self
        messages = alice.recv(wait=1, include_self=False)
        self.assertEqual(len(messages), 0)

        # With include_self
        messages = alice.recv(wait=1, unread_only=False, include_self=True)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["body"], "To Self")

    def test_peek(self):
        """Test peeking at messages."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Message 1")
        alice.send("bob", "Message 2")

        # Peek doesn't mark as read
        messages = bob.peek(limit=10)
        self.assertEqual(len(messages), 2)

        # Recv still sees them as unread
        messages = bob.recv(wait=1)
        self.assertEqual(len(messages), 2)

    def test_list_peers(self):
        """Test listing peers."""
        alice = A2AClient(self.project, "alice")
        peers = alice.list_peers()

        self.assertEqual(len(peers), 2)
        peer_ids = {p["id"] for p in peers}
        self.assertIn("alice", peer_ids)
        self.assertIn("bob", peer_ids)

    def test_set_status(self):
        """Test setting agent status."""
        alice = A2AClient(self.project, "alice")

        alice.set_status("done")
        status = alice.get_status("alice")
        self.assertEqual(status, "done")

    def test_get_status(self):
        """Test getting agent status."""
        alice = A2AClient(self.project, "alice")

        status = alice.get_status()
        self.assertEqual(status, "active")

        status = alice.get_status("bob")
        self.assertEqual(status, "active")

    def test_wait_for_messages(self):
        """Test waiting for messages."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        # Send message in a thread-like way
        alice.send("bob", "Message 1")
        alice.send("bob", "Message 2")

        # Wait for 2 messages
        result = bob.wait_for_messages(count=2, timeout=5)
        self.assertTrue(result)

    def test_search(self):
        """Test searching messages."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Hello world")
        alice.send("bob", "Hello universe")
        bob.send("alice", "Goodbye world")

        # Search for "hello"
        results = alice.search("hello", limit=10)
        self.assertEqual(len(results), 2)
        self.assertIn("Hello", results[0]["body"])

    def test_search_case_insensitive(self):
        """Test that search is case-insensitive."""
        alice = A2AClient(self.project, "alice")

        alice.send("bob", "Test MESSAGE")
        alice.send("bob", "Another test")

        results = alice.search("message", limit=10)
        self.assertEqual(len(results), 1)
        self.assertIn("Test MESSAGE", results[0]["body"])

    def test_thread(self):
        """Test retrieving a thread."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        # Send messages with same thread_id
        conn = sqlite3.connect(str(self.project_dir / "database.db"))
        ts = time.time()
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", "bob", "Message 1", "thread-123", ts),
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) "
            "VALUES (?,?,?,?,?)",
            ("bob", "alice", "Message 2", "thread-123", ts + 1),
        )
        conn.commit()
        conn.close()

        # Retrieve thread
        messages = alice.thread("thread-123")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["body"], "Message 1")
        self.assertEqual(messages[1]["body"], "Message 2")

    def test_stats(self):
        """Test getting bus statistics."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Direct message")
        alice.send("all", "Broadcast message")
        bob.send("alice", "Reply")

        stats = alice.stats()
        self.assertEqual(stats["messages"], 3)
        self.assertEqual(stats["direct_messages"], 2)
        self.assertEqual(stats["broadcasts"], 1)
        self.assertEqual(stats["agents_active"], 2)

    def test_stats_top_senders(self):
        """Test stats include top senders."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        for i in range(3):
            alice.send("bob", f"Message {i}")
        bob.send("alice", "Reply")

        stats = alice.stats()
        self.assertGreater(len(stats["top_senders"]), 0)
        # alice should be the top sender
        self.assertEqual(stats["top_senders"][0]["agent"], "alice")
        self.assertEqual(stats["top_senders"][0]["count"], 3)

    def test_recv_with_limit(self):
        """Test recv respects the limit parameter."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        for i in range(5):
            alice.send("bob", f"Message {i}")

        messages = bob.recv(wait=1, limit=3)
        self.assertEqual(len(messages), 3)

    def test_peek_empty(self):
        """Test peek on empty bus returns empty list."""
        alice = A2AClient(self.project, "alice")
        messages = alice.peek()
        self.assertEqual(messages, [])

    def test_get_status_unknown_agent(self):
        """Test get_status returns None for unknown agent."""
        alice = A2AClient(self.project, "alice")
        status = alice.get_status("nonexistent-agent")
        self.assertIsNone(status)

    def test_set_status_nonexistent_agent_is_noop(self):
        """set_status on unknown agent silently does nothing."""
        ghost = A2AClient(self.project, "ghost-agent")
        # Should not raise; UPDATE WHERE id=? with no matching row is a no-op
        ghost.set_status("done")
        # Confirm ghost was never actually registered
        alice = A2AClient(self.project, "alice")
        self.assertIsNone(alice.get_status("ghost-agent"))

    def test_wait_for_messages_returns_false_on_timeout(self):
        """wait_for_messages returns False when messages never arrive."""
        bob = A2AClient(self.project, "bob")
        # No messages sent — should timeout quickly
        result = bob.wait_for_messages(count=1, timeout=0.3)
        self.assertFalse(result)

    def test_search_returns_empty_when_no_match(self):
        """search returns [] when query has no matching messages."""
        alice = A2AClient(self.project, "alice")
        alice.send("bob", "Hello world")
        results = alice.search("zzznomatch")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
