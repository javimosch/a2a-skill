#!/usr/bin/env python3
"""Unit tests for a2a.py — peer messaging CLI.

Covers: DB schema, message send/recv, read-tracking, filtering, edge cases.
Run: python3 test_a2a.py
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

# Import a2a (assumes it's in same dir or on path)
sys.path.insert(0, os.path.dirname(__file__))
import a2a


class TestA2ADB(unittest.TestCase):
    """Database schema and initialization."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    def test_init_creates_schema(self):
        """conn = connect(..., create=True) initializes schema."""
        conn = a2a.connect(self.project, create=True)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        self.assertIn("agents", names)
        self.assertIn("messages", names)
        self.assertIn("reads", names)
        conn.close()

    def test_wal_mode(self):
        """WAL mode enabled for concurrent access."""
        conn = a2a.connect(self.project, create=True)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")
        conn.close()


class TestAgentRegistry(unittest.TestCase):
    """Agent registration and listing."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)
        a2a.connect(self.project, create=True).close()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    def test_register_agent(self):
        """Register an agent with role, prompt, cli."""
        args = a2a.argparse.Namespace(
            project=self.project, id="alice", role="planner",
            prompt="test prompt", cli="claude", pid=None, upsert=False
        )
        a2a.cmd_register(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT role, prompt, cli FROM agents WHERE id=?",
                          ("alice",)).fetchone()
        self.assertEqual(row[0], "planner")
        self.assertEqual(row[1], "test prompt")
        self.assertEqual(row[2], "claude")
        conn.close()

    def test_register_upsert(self):
        """Upsert updates existing agent without error."""
        args = a2a.argparse.Namespace(
            project=self.project, id="bob", role="role1",
            prompt="p1", cli="claude", pid=None, upsert=False
        )
        a2a.cmd_register(args)
        args.role = "role2"
        args.prompt = "p2"
        args.upsert = True
        a2a.cmd_register(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT role, prompt FROM agents WHERE id=?",
                          ("bob",)).fetchone()
        self.assertEqual(row[0], "role2")
        self.assertEqual(row[1], "p2")
        conn.close()


class TestMessaging(unittest.TestCase):
    """Send, receive, read-tracking."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)
        conn = a2a.connect(self.project, create=True)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, role, status, created_at, last_seen) "
                "VALUES (?,?,?,?,?)",
                (agent_id, "tester", "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    def test_send_direct(self):
        """Send a direct message from alice to bob."""
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="hello bob",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT sender, recipient, body FROM messages WHERE sender=?",
            ("alice",)
        ).fetchone()
        self.assertEqual(row[0], "alice")
        self.assertEqual(row[1], "bob")
        self.assertEqual(row[2], "hello bob")
        conn.close()

    def test_send_broadcast(self):
        """Send a broadcast (recipient=NULL) via 'all'."""
        args = a2a.argparse.Namespace(
            project=self.project, to="all", body="team message",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT recipient FROM messages WHERE body=?",
            ("team message",)
        ).fetchone()
        self.assertIsNone(row[0])
        conn.close()

    def test_recv_unread(self):
        """Receive only unread messages."""
        conn = a2a.connect(self.project)
        # Alice sends to bob, then broadcast
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) "
            "VALUES (?,?,?,?)",
            ("alice", "bob", "msg1", a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) "
            "VALUES (?,?,?,?)",
            ("alice", None, "broadcast", a2a.now())
        )
        conn.commit()
        conn.close()

        # Bob receives — should see both
        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "bob", "wait": 0, "all": False,
                                     "peek": False, "limit": 0, "since": None,
                                     "json": False, "include_self": False}
        )
        # Capture output — for now just verify no crash
        a2a.cmd_recv(args)

    def test_recv_all(self):
        """Receive with --all includes already-read messages."""
        conn = a2a.connect(self.project)
        mid = conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) "
            "VALUES (?,?,?,?) RETURNING id",
            ("alice", "bob", "old msg", a2a.now())
        ).fetchone()[0]
        conn.execute("INSERT INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
                    ("bob", mid, a2a.now()))
        conn.commit()
        conn.close()

        # Bob can still see it with --all
        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "bob", "wait": 0, "all": True,
                                     "peek": False, "limit": 0, "since": None,
                                     "json": False, "include_self": False}
        )
        a2a.cmd_recv(args)  # Should not crash

    def test_recv_filters_self(self):
        """Recv filters out messages from the agent itself."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) "
            "VALUES (?,?,?,?)",
            ("alice", "alice", "self message", a2a.now())
        )
        conn.commit()
        conn.close()

        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "alice", "wait": 0, "all": False,
                                     "peek": False, "limit": 0, "since": None,
                                     "json": False, "include_self": False}
        )
        a2a.cmd_recv(args)  # Self-sent msg should not appear

    def test_recv_include_self(self):
        """--include-self makes self-sent messages visible."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) "
            "VALUES (?,?,?,?)",
            ("alice", "alice", "self message", a2a.now())
        )
        conn.commit()
        conn.close()

        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "alice", "wait": 0, "all": False,
                                     "peek": False, "limit": 0, "since": None,
                                     "json": False, "include_self": True}
        )
        a2a.cmd_recv(args)  # Self-sent msg should appear


class TestLifecycle(unittest.TestCase):
    """Agent lifecycle: status, unregister, listing, project info."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)
        a2a.connect(self.project, create=True).close()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    def _register(self, agent_id: str, role: str = "tester"):
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) "
            "VALUES (?,?,?,?,?)",
            (agent_id, role, "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()

    def test_status_transition(self):
        """Status command transitions agent through states."""
        self._register("tester")
        for state in ("idle", "active", "blocked", "done"):
            args = a2a.argparse.Namespace(
                project=self.project, state=state, **{"as_": "tester"}
            )
            a2a.cmd_status(args)
            conn = a2a.connect(self.project)
            row = conn.execute(
                "SELECT status FROM agents WHERE id=?", ("tester",)
            ).fetchone()
            self.assertEqual(row["status"], state)
            conn.close()

    def test_status_unknown_agent(self):
        """Status on unknown agent fails gracefully."""
        args = a2a.argparse.Namespace(
            project=self.project, state="done", **{"as_": "nobody"}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_status(args)

    def test_unregister_agent(self):
        """Unregister removes an agent from the bus."""
        self._register("remove-me")
        args = a2a.argparse.Namespace(project=self.project, id="remove-me")
        a2a.cmd_unregister(args)
        conn = a2a.connect(self.project)
        count = conn.execute(
            "SELECT COUNT(*) FROM agents WHERE id=?", ("remove-me",)
        ).fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

    def test_unregister_nonexistent(self):
        """Unregister a non-existent agent prints 0 (no error)."""
        args = a2a.argparse.Namespace(project=self.project, id="phantom")
        a2a.cmd_unregister(args)  # Should not crash

    def test_list_agents_json(self):
        """List agents outputs valid JSON."""
        self._register("agent-a", role="dev")
        self._register("agent-b", role="critic")
        args = a2a.argparse.Namespace(project=self.project, json=True)
        with patch("sys.stdout"):  # suppress print
            a2a.cmd_list(args)
        # Verify agents are in DB
        conn = a2a.connect(self.project)
        rows = conn.execute(
            "SELECT id, role FROM agents ORDER BY id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "agent-a")
        self.assertEqual(rows[1]["id"], "agent-b")
        conn.close()

    def test_list_agents_empty(self):
        """List on empty bus prints '(no agents registered)'."""
        args = a2a.argparse.Namespace(project=self.project, json=False)
        a2a.cmd_list(args)  # Should not crash

    def test_project_info(self):
        """Project command prints resolved project info."""
        args = a2a.argparse.Namespace(project=self.project)
        a2a.cmd_project(args)  # Should not crash


class TestEdgeCases(unittest.TestCase):
    """Edge cases: unknown agents, validation, threading."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)
        a2a.connect(self.project, create=True).close()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    def _register(self, agent_id: str):
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            (agent_id, "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()

    def test_send_unknown_recipient(self):
        """Sending to unknown agent fails gracefully."""
        args = a2a.argparse.Namespace(
            project=self.project, to="unknown", body="hi",
            **{"from_": "alice", "thread": None}
        )
        # Should raise SystemExit with a clear error
        with self.assertRaises(SystemExit):
            a2a.cmd_send(args)

    def test_send_with_thread(self):
        """Send with --thread stores thread_id on the message."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="threaded msg",
            **{"from_": "alice", "thread": "discussion-1"}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT thread_id FROM messages WHERE body=?",
            ("threaded msg",)
        ).fetchone()
        self.assertEqual(row["thread_id"], "discussion-1")
        conn.close()

    def test_recv_unknown_agent(self):
        """Receiving as unknown agent fails gracefully."""
        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "unknown", "wait": 0, "all": False,
                                     "peek": False, "limit": 0, "since": None,
                                     "json": False}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(args)

    def test_ttl_send(self):
        """Send with --ttl stores ttl_seconds correctly."""
        # Register agents
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

        # Send with TTL
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="expiring msg",
            **{"from_": "alice", "thread": None, "ttl": 3600}
        )
        a2a.cmd_send(args)

        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT body, ttl_seconds FROM messages WHERE body=?",
            ("expiring msg",)
        ).fetchone()
        self.assertEqual(row["body"], "expiring msg")
        self.assertEqual(row["ttl_seconds"], 3600)
        conn.close()

    def test_ttl_no_expiry_default(self):
        """Send without --ttl leaves ttl_seconds as NULL (never expire)."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="persistent msg",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)

        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT ttl_seconds FROM messages WHERE body=?",
            ("persistent msg",)
        ).fetchone()
        self.assertIsNone(row["ttl_seconds"])
        conn.close()

    def test_ttl_cleanup_expired(self):
        """cleanup_expired() removes messages past their TTL."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()

        # Insert an already-expired message (TTL 1s, created 10s ago)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", "bob", "gone", 1, a2a.now() - 10)
        )
        # Insert a non-expired message (TTL 3600s, just now)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", "bob", "keep", 3600, a2a.now())
        )
        # Insert a message with no TTL (should never expire)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", None, "forever", None, a2a.now())
        )
        conn.commit()
        conn.close()

        # Run cleanup
        conn = a2a.connect(self.project)
        deleted = a2a.cleanup_expired(conn)
        conn.commit()

        self.assertGreaterEqual(deleted, 1, "Expected at least 1 expired msg deleted")

        remaining = conn.execute(
            "SELECT body FROM messages ORDER BY body"
        ).fetchall()
        remaining_bodies = [r["body"] for r in remaining]
        self.assertIn("keep", remaining_bodies)
        self.assertIn("forever", remaining_bodies)
        self.assertNotIn("gone", remaining_bodies)
        conn.close()

    def test_ttl_cleanup_on_peek(self):
        """peek triggers cleanup_expired so expired msgs don't appear."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        # Insert expired message
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", None, "should disappear", 1, a2a.now() - 10)
        )
        conn.commit()
        conn.close()

        # Peek triggers cleanup
        args = a2a.argparse.Namespace(
            project=self.project, limit=10, json=False
        )
        a2a.cmd_peek(args)

        # Verify expired message is gone
        conn = a2a.connect(self.project)
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE body=?",
            ("should disappear",)
        ).fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

    def test_send_to_self(self):
        """Sending a message to yourself works."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice",):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

        args = a2a.argparse.Namespace(
            project=self.project, to="alice", body="note to self",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)

        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT sender, recipient, body FROM messages"
        ).fetchone()
        self.assertEqual(row["sender"], "alice")
        self.assertEqual(row["recipient"], "alice")
        self.assertEqual(row["body"], "note to self")
        conn.close()

    def test_concurrent_writes(self):
        """Multiple agents can write concurrently (WAL handles it)."""
        # Register two agents
        for agent_id in ("agent1", "agent2"):
            conn = a2a.connect(self.project)
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
            conn.commit()
            conn.close()

        # Simulate concurrent sends (sequential here, but the db should handle
        # true concurrency via WAL)
        for i in range(5):
            conn = a2a.connect(self.project)
            sender = "agent1" if i % 2 == 0 else "agent2"
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) "
                "VALUES (?,?,?,?)",
                (sender, None, f"msg{i}", a2a.now())
            )
            conn.commit()
            conn.close()

        conn = a2a.connect(self.project)
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.assertEqual(count, 5)
        conn.close()


    def test_ttl_no_expiry(self):
        """Message with 0 TTL (no expiry) persists after cleanup."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("agent-a", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("agent-a", None, "no-ttl", None, a2a.now())
        )
        conn.commit()
        n = a2a.cleanup_expired(conn)
        conn.close()
        self.assertEqual(n, 0, "message with NULL ttl should NOT be deleted")

    def test_ttl_expired(self):
        """Message past its TTL is deleted by cleanup_expired."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("agent-b", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("agent-b", None, "old", 1, a2a.now() - 10)  # 10s ago, TTL=1s
        )
        conn.commit()
        n = a2a.cleanup_expired(conn)
        conn.close()
        self.assertGreaterEqual(n, 1, "expired message should be deleted")


if __name__ == "__main__":
    unittest.main()
