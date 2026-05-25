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

    def test_constructor_empty_agent_id_raises_error(self):
        """A2AClient with empty agent_id raises ValueError."""
        with self.assertRaises(ValueError):
            A2AClient(self.project, "")
        with self.assertRaises(ValueError):
            A2AClient(self.project, "   ")

    def test_constructor_empty_project_raises_error(self):
        """A2AClient with empty project raises ValueError."""
        with self.assertRaises(ValueError):
            A2AClient("", "alice")
        with self.assertRaises(ValueError):
            A2AClient("   ", "alice")

    def test_constructor_agent_id_too_long_raises_error(self):
        """A2AClient with agent_id > 256 chars raises ValueError."""
        with self.assertRaises(ValueError):
            A2AClient(self.project, "a" * 300)

    def test_send_thread_id_too_long_raises_error(self):
        """send() with thread_id > 256 chars raises ValueError."""
        alice = A2AClient(self.project, "alice")
        alice.register("tester")
        with self.assertRaises(ValueError):
            alice.send("bob", "test", thread_id="t" * 300)

    def test_send_body_too_long_raises_error(self):
        """send() with body > 100000 chars raises ValueError."""
        alice = A2AClient(self.project, "alice")
        alice.register("tester")
        with self.assertRaises(ValueError):
            alice.send("bob", "x" * 100_001)

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

    def test_set_status_invalid_raises_error(self):
        """set_status() with invalid status raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.set_status("invalid_status")
        with self.assertRaises(ValueError):
            alice.set_status("")
        # Valid statuses should still work
        alice.set_status("active")
        alice.set_status("idle")
        alice.set_status("done")
        alice.set_status("blocked")

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

    def test_wait_for_messages_staggered(self):
        """wait_for_messages with count > 1 works when messages arrive one at a time."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        # Send first message
        alice.send("bob", "First message")
        # Wait slightly for it to be stored
        time.sleep(0.05)
        # Send second message after a gap
        alice.send("bob", "Second message")

        # Wait for both — the fix accumulates across polls
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

    def test_search_empty_query_raises_value_error(self):
        """search with empty string raises ValueError."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "Message two")
        with self.assertRaises(ValueError):
            alice.search("", limit=10)
        with self.assertRaises(ValueError):
            alice.search("   ", limit=10)

    def test_search_non_positive_limit_raises_value_error(self):
        """search with non-positive limit raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.search("hello", limit=0)
        with self.assertRaises(ValueError):
            alice.search("hello", limit=-1)

    def test_search_special_characters(self):
        """search handles special characters in query."""
        alice = A2AClient(self.project, "alice")
        alice.send("bob", "price is $100.00 + tax (15%)")
        alice.send("bob", "C:\\Users\\test\\path")
        results = alice.search("$100", limit=10)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("$100", results[0]["body"])
        results2 = alice.search("C:\\Users", limit=10)
        self.assertGreaterEqual(len(results2), 1)
        self.assertIn("C:\\Users", results2[0]["body"])

    def test_search_with_limit(self):
        """search respects the limit parameter."""
        alice = A2AClient(self.project, "alice")
        for i in range(10):
            alice.send("bob", f"searchable message {i}")
        results = alice.search("searchable", limit=3)
        self.assertLessEqual(len(results), 3)

    def test_thread_returns_empty_for_nonexistent_thread(self):
        """thread() returns [] when thread_id has no messages."""
        alice = A2AClient(self.project, "alice")
        messages = alice.thread("nonexistent-thread-id")
        self.assertEqual(messages, [])

    def test_stats_empty_bus(self):
        """stats() works correctly on a bus with no messages."""
        alice = A2AClient(self.project, "alice")
        stats = alice.stats()
        self.assertEqual(stats["messages"], 0)
        self.assertEqual(stats["direct_messages"], 0)
        self.assertEqual(stats["broadcasts"], 0)
        self.assertEqual(stats["threads"], 0)
        self.assertEqual(stats["top_senders"], [])

    def test_list_peers_reflects_status_changes(self):
        """list_peers shows updated status after set_status call."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        bob.set_status("done")
        peers = alice.list_peers()
        peer_map = {p["id"]: p for p in peers}
        self.assertEqual(peer_map["alice"]["status"], "active")
        self.assertEqual(peer_map["bob"]["status"], "done")

    def test_send_with_thread_id(self):
        """send() stores thread_id on message."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        msg_id = alice.send("bob", "threaded msg", thread_id="t-99")
        self.assertGreater(msg_id, 0)
        thread_msgs = bob.thread("t-99")
        self.assertEqual(len(thread_msgs), 1)
        self.assertEqual(thread_msgs[0]["body"], "threaded msg")

    def test_register_adds_agent(self):
        """register() inserts agent into the DB."""
        client = A2AClient(self.project, "new-agent-x")
        result = client.register("tester", cli="pytest")
        self.assertTrue(result)
        peers = A2AClient(self.project, "alice").list_peers()
        ids = {p["id"] for p in peers}
        self.assertIn("new-agent-x", ids)

    def test_unregister_removes_agent(self):
        """unregister() deletes agent from DB."""
        client = A2AClient(self.project, "temp-agent-y")
        client.register("temp")
        client.unregister()
        peers = A2AClient(self.project, "alice").list_peers()
        ids = {p["id"] for p in peers}
        self.assertNotIn("temp-agent-y", ids)

    def test_register_stores_all_fields(self):
        """register() persists role, prompt, cli, and pid."""
        client = A2AClient(self.project, "detail-agent")
        client.register("analyst", prompt="analyze data", cli="pytest", pid=9999)
        peers = client.list_peers()
        peer = next(p for p in peers if p["id"] == "detail-agent")
        self.assertEqual(peer["role"], "analyst")
        self.assertEqual(peer["cli"], "pytest")
        self.assertEqual(peer["pid"], 9999)

    def test_unregister_nonexistent_is_noop(self):
        """unregister() on unknown agent silently returns True."""
        client = A2AClient(self.project, "never-registered-agent")
        result = client.unregister()
        self.assertTrue(result)

    def test_send_with_thread_id_groups_messages(self):
        """send() with same thread_id groups multiple messages into one thread."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        alice.send("bob", "thread msg 1", thread_id="group-1")
        alice.send("bob", "thread msg 2", thread_id="group-1")
        alice.send("bob", "no thread msg")
        thread_msgs = bob.thread("group-1")
        self.assertEqual(len(thread_msgs), 2)
        self.assertTrue(all(m["thread_id"] == "group-1" for m in thread_msgs))

    def test_register_returns_true_on_upsert(self):
        """register() with upsert=True updates an existing agent and returns True."""
        alice = A2AClient(self.project, "alice")
        result = alice.register("planner", upsert=True)
        self.assertTrue(result)
        # Role should be updated
        peers = alice.list_peers()
        peer = next(p for p in peers if p["id"] == "alice")
        self.assertEqual(peer["role"], "planner")

    def test_register_upsert_preserves_created_at(self):
        """register() with upsert=True preserves original created_at timestamp."""
        import time
        alice = A2AClient(self.project, "alice")
        # First registration
        alice.register("critic", upsert=True)
        # Read back the created_at
        import sqlite3
        conn = sqlite3.connect(str(alice.db_path))
        row = conn.execute("SELECT created_at FROM agents WHERE id='alice'").fetchone()
        original_created = row[0]
        conn.close()
        # Small delay to ensure different timestamps
        time.sleep(0.01)
        # Upsert with different role
        alice.register("planner", upsert=True)
        conn = sqlite3.connect(str(alice.db_path))
        row = conn.execute("SELECT created_at, role, last_seen FROM agents WHERE id='alice'").fetchone()
        conn.close()
        # created_at must be preserved
        self.assertEqual(row[0], original_created)
        # role must be updated
        self.assertEqual(row[1], "planner")
        # last_seen must be updated (greater than original)
        self.assertGreater(row[2], original_created)

    def test_register_duplicate_raises_without_upsert(self):
        """register() without upsert on existing agent raises IntegrityError."""
        alice = A2AClient(self.project, "alice")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            alice.register("tester", upsert=False)

    def test_peek_respects_limit(self):
        """peek() returns at most limit messages."""
        alice = A2AClient(self.project, "alice")
        for i in range(10):
            alice.send("bob", f"peek-limit-msg-{i}")
        messages = alice.peek(limit=3)
        self.assertLessEqual(len(messages), 3)

    def test_recv_chronological_order(self):
        """recv returns messages in chronological order."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        import time
        alice.send("bob", "first")
        time.sleep(0.01)
        alice.send("bob", "second")
        time.sleep(0.01)
        alice.send("bob", "third")
        messages = bob.recv(wait=1, limit=3)
        bodies = [m["body"] for m in messages]
        self.assertEqual(bodies, ["first", "second", "third"])

    def test_send_empty_body(self):
        """send() with empty body creates a message with empty content."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        msg_id = alice.send("bob", "")
        self.assertGreater(msg_id, 0)
        messages = bob.recv(wait=1)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["body"], "")

    def test_send_ttl_non_positive_rejected(self):
        """send() with ttl_seconds <= 0 raises ValueError."""
        alice = A2AClient(self.project, "alice")
        for bad_ttl in (0, -1, -5):
            with self.assertRaises(ValueError):
                alice.send("bob", "bad ttl", ttl_seconds=bad_ttl)
        # Verify no messages were stored
        messages = alice.peek(limit=10)
        self.assertEqual(len(messages), 0, "no messages with non-positive TTL should be stored")

    def test_peek_cleans_up_expired_messages(self):
        """peek() triggers TTL cleanup so expired messages don't appear."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        alice.send("bob", "ttl will expire", ttl_seconds=1)
        time.sleep(1.2)
        # peek should clean up the expired message
        messages = bob.peek(limit=10)
        bodies = [m["body"] for m in messages]
        self.assertNotIn("ttl will expire", bodies)

    def test_wait_for_messages_count_zero_raises_error(self):
        """wait_for_messages(count=0) raises ValueError (must be positive)."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError):
            bob.wait_for_messages(count=0, timeout=5)

    def test_wait_for_messages_negative_count_raises_error(self):
        """wait_for_messages with negative count raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError):
            bob.wait_for_messages(count=-1, timeout=5)

    def test_wait_for_messages_negative_timeout_raises_error(self):
        """wait_for_messages with negative timeout raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError):
            bob.wait_for_messages(count=1, timeout=-1)

    def test_list_peers_empty(self):
        """list_peers() returns all registered agents on the bus."""
        # setUp registers alice and bob
        alice = A2AClient(self.project, "alice")
        peers = alice.list_peers()
        self.assertIsInstance(peers, list)
        # At minimum alice and bob should be present
        ids = [p["id"] for p in peers]
        self.assertIn("alice", ids)
        self.assertIn("bob", ids)

    def test_send_to_self_with_include_self(self):
        """send() to own ID and recv with include_self shows the message."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        msg_id = alice.send("alice", "hello self")
        self.assertGreater(msg_id, 0)
        # Normal recv should not include self-messages
        msgs = alice.recv(wait=1, unread_only=False)
        self.assertNotIn("hello self", [m["body"] for m in msgs])
        # With include_self=True, it should be visible
        msgs_with_self = alice.recv(wait=0, unread_only=True, include_self=True)
        self.assertIn("hello self", [m["body"] for m in msgs_with_self])

    def test_send_very_long_body(self):
        """Send with a very long message body."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        long_body = "A" * 10000
        msg_id = alice.send("bob", long_body)
        self.assertGreater(msg_id, 0)
        msgs = bob.recv(wait=1)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(len(msgs[0]["body"]), 10000)
        self.assertEqual(msgs[0]["body"], long_body)

    def test_thread_empty_string_id_raises_error(self):
        """thread() raises ValueError when thread_id is an empty string."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.thread("")

    def test_thread_whitespace_id_raises_error(self):
        """thread() raises ValueError when thread_id is whitespace."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.thread("   ")

    def test_search_special_chars_query(self):
        """search() handles special LIKE characters in the query string."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        alice.send("bob", "testing 100% complete")
        alice.send("bob", "under_score_value")
        alice.send("bob", "normal query")
        # % and _ should not be treated as wildcards in FTS search
        result_pct = alice.search("100%")
        bodies = [m["body"] for m in result_pct]
        self.assertIn("testing 100% complete", bodies)
        result_underscore = alice.search("under_score")
        bodies2 = [m["body"] for m in result_underscore]
        self.assertIn("under_score_value", bodies2)

    def test_recv_empty_wait_returns_immediately(self):
        """recv() with wait=0 returns immediately without blocking."""
        bob = A2AClient(self.project, "bob")
        import time
        start = time.time()
        messages = bob.recv(wait=0)
        elapsed = time.time() - start
        self.assertEqual(len(messages), 0)
        self.assertLess(elapsed, 2, "recv with wait=0 should not block")

    def test_peek_limit_non_positive_rejected(self):
        """peek() with limit <= 0 raises ValueError."""
        alice = A2AClient(self.project, "alice")
        for bad_limit in (0, -1):
            with self.assertRaises(ValueError):
                alice.peek(limit=bad_limit)

    def test_send_to_empty_string(self):
        """send() with empty or whitespace-only recipient raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.send("", "empty recipient")
        with self.assertRaises(ValueError):
            alice.send("   ", "whitespace only")

    def test_recv_negative_wait_returns_immediately(self):
        """recv() with negative wait raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError) as ctx:
            bob.recv(wait=-1)
        self.assertIn("non-negative", str(ctx.exception))

    def test_recv_nan_wait_raises_value_error(self):
        """recv() with NaN wait raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError) as ctx:
            bob.recv(wait=float("nan"))
        self.assertIn("finite", str(ctx.exception))

    def test_recv_inf_wait_raises_value_error(self):
        """recv() with inf wait raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError) as ctx:
            bob.recv(wait=float("inf"))
        self.assertIn("finite", str(ctx.exception))

    def test_wait_for_messages_nan_timeout_raises_value_error(self):
        """wait_for_messages with NaN timeout raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError) as ctx:
            bob.wait_for_messages(count=1, timeout=float("nan"))
        self.assertIn("finite", str(ctx.exception))

    def test_cross_project_isolation(self):
        """Messages in project A do not leak into project B."""
        import shutil
        # Create a second project
        project_b = f"client-proj-b-{id(self)}"
        proj_dir_b = Path.home() / ".a2a" / project_b
        proj_dir_b.mkdir(parents=True, exist_ok=True)

        # Set up second project's database (same schema, different db file)
        db_path_b = proj_dir_b / "database.db"
        conn_b = sqlite3.connect(str(db_path_b))
        conn_b.executescript("""
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
        ts = time.time()
        conn_b.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) VALUES (?,?,?,?,?)",
            ("alice", "tester", "active", ts, ts),
        )
        conn_b.commit()
        conn_b.close()

        # Project A alice sends a message
        alice_a = A2AClient(self.project, "alice")
        alice_a.send("bob", "secret from A")

        # Project B alice should not see it
        alice_b = A2AClient(project_b, "alice")
        msgs_b = alice_b.recv(wait=0)
        bodies_b = [m["body"] for m in msgs_b]
        self.assertNotIn("secret from A", bodies_b, "messages should not cross projects")

        # Clean up project B
        if db_path_b.exists():
            db_path_b.unlink()
        if proj_dir_b.exists():
            shutil.rmtree(proj_dir_b)

    def test_negative_limit_raises_error(self):
        """recv() with negative limit raises ValueError."""
        bob = A2AClient(self.project, "bob")
        with self.assertRaises(ValueError) as ctx:
            bob.recv(wait=0, limit=-5)
        self.assertIn("non-negative", str(ctx.exception))

    def test_register_non_positive_pid_raises_error(self):
        """register() with non-positive pid raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.register("tester", pid=0)
        with self.assertRaises(ValueError):
            alice.register("tester", pid=-1)

    def test_recv_unread_only_false_returns_read_messages(self):
        """recv with unread_only=False returns already-read messages."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")

        alice.send("bob", "message to read")
        # First recv reads and marks as read
        first = bob.recv(wait=1)
        self.assertEqual(len(first), 1)
        # Second recv with unread_only=False should still return it
        second = bob.recv(wait=0, unread_only=False)
        self.assertGreaterEqual(len(second), 1)
        self.assertIn("message to read", [m["body"] for m in second])

    def test_send_ttl_with_thread_combined(self):
        """send with both ttl_seconds and thread_id works together."""
        alice = A2AClient(self.project, "alice")
        bob = A2AClient(self.project, "bob")
        msg_id = alice.send("bob", "threaded ttl msg", thread_id="ttl-thread-1", ttl_seconds=3600)
        self.assertGreater(msg_id, 0)
        # Verify thread and TTL were stored
        import sqlite3
        conn = sqlite3.connect(str(alice.db_path))
        row = conn.execute(
            "SELECT thread_id, ttl_seconds FROM messages WHERE id=?", (msg_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "ttl-thread-1")
        self.assertEqual(row[1], 3600)

    def test_search_empty_result(self):
        """search returns empty list when no messages match."""
        alice = A2AClient(self.project, "alice")
        results = alice.search("nonexistent-term-xyz")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_send_nan_ttl_raises_value_error(self):
        """send with NaN ttl raises ValueError."""
        alice = A2AClient(self.project, "alice")
        alice.register("tester")
        with self.assertRaises(ValueError):
            alice.send("bob", "hello", ttl_seconds=float("nan"))

    def test_send_inf_ttl_raises_value_error(self):
        """send with inf ttl raises ValueError."""
        alice = A2AClient(self.project, "alice")
        alice.register("tester")
        with self.assertRaises(ValueError):
            alice.send("bob", "hello", ttl_seconds=float("inf"))

    def test_register_role_too_long_raises_value_error(self):
        """register with role > 256 chars raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.register(role="x" * 300)

    def test_register_cli_too_long_raises_value_error(self):
        """register with cli > 128 chars raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.register(role="tester", cli="c" * 200)

    def test_register_prompt_too_long_raises_value_error(self):
        """register with prompt > 100K chars raises ValueError."""
        alice = A2AClient(self.project, "alice")
        with self.assertRaises(ValueError):
            alice.register(role="tester", prompt="p" * 100_001)


if __name__ == "__main__":
    unittest.main()
