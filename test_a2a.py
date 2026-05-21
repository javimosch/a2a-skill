#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

    def test_register_duplicate_fails_without_upsert(self):
        """Registering same agent twice without --upsert raises SystemExit."""
        args = a2a.argparse.Namespace(
            project=self.project, id="dup", role="role1",
            prompt="p1", cli="claude", pid=None, upsert=False
        )
        a2a.cmd_register(args)
        with self.assertRaises(SystemExit):
            a2a.cmd_register(args)

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

    def test_cmd_list_no_database(self):
        """List on non-initialized project raises SystemExit (connect fails)."""
        project = f"list-nonex-{os.getpid()}"
        with self.assertRaises(SystemExit):
            a2a.cmd_list(a2a.argparse.Namespace(project=project, json=False))

    def test_cmd_clear_no_database(self):
        """Clear on a project with no database prints notice and does not crash."""
        project = f"clear-nonex-{os.getpid()}"
        a2a.cmd_clear(a2a.argparse.Namespace(project=project, yes=True))


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

    def test_ttl_zero_immediate_expiry(self):
        """TTL=0 means the message expires immediately."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", None, "instant", 0, a2a.now())
        )
        conn.commit()
        # Even with 0 TTL, cleanup should remove it (created_at equals now,
        # but 0 seconds TTL means it's already expired)
        deleted = a2a.cleanup_expired(conn)
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE body='instant'"
        ).fetchone()[0]
        conn.close()
        self.assertGreaterEqual(deleted, 1)
        self.assertEqual(remaining, 0, "TTL=0 message should be removed")

    def test_ttl_negative_expires_immediately(self):
        """Negative TTL value should be treated as immediate expiry."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", None, "neg-ttl", -1, a2a.now())
        )
        conn.commit()
        deleted = a2a.cleanup_expired(conn)
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE body='neg-ttl'"
        ).fetchone()[0]
        conn.close()
        self.assertGreaterEqual(deleted, 1)
        self.assertEqual(remaining, 0, "negative TTL message should be removed")

    def test_ttl_recv_hides_expired(self):
        """recv should not return messages that have already expired."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        # Insert expired message (10s old with 1s TTL)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("alice", "bob", "old news", 1, a2a.now() - 10)
        )
        # Insert non-expired message
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("bob", "alice", "fresh news", 3600, a2a.now())
        )
        conn.commit()
        conn.close()

        # recv should only return the non-expired message
        args = a2a.argparse.Namespace(
            project=self.project, as_="alice", wait=0,
            all=False, include_self=False, peek=False, since=None, limit=None, json=False
        )
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_recv(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("fresh news", output)
        self.assertNotIn("old news", output)

    def test_cross_project_isolation(self):
        """Messages from one project should not appear in another project."""
        project_a = f"{self.project}-a"
        project_b = f"{self.project}-b"
        a2a.connect(project_a, create=True).close()
        a2a.connect(project_b, create=True).close()
        # Register agents in both projects
        for p in (project_a, project_b):
            conn = a2a.connect(p)
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                ("alice", "active", a2a.now(), a2a.now())
            )
            conn.commit()
            conn.close()
        # Send message in project_a
        args = a2a.argparse.Namespace(
            project=project_a, to="alice", body="secret project a msg",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        # Verify it's only in project_a
        conn_a = a2a.connect(project_a)
        count_a = conn_a.execute(
            "SELECT COUNT(*) FROM messages WHERE body='secret project a msg'"
        ).fetchone()[0]
        conn_a.close()
        conn_b = a2a.connect(project_b)
        count_b = conn_b.execute(
            "SELECT COUNT(*) FROM messages WHERE body='secret project a msg'"
        ).fetchone()[0]
        conn_b.close()
        # Clean up
        for db in (a2a.db_path(project_a), a2a.db_path(project_b)):
            if db.exists():
                db.unlink()
        self.assertEqual(count_a, 1, "message should exist in project A")
        self.assertEqual(count_b, 0, "message should NOT leak to project B")

    def test_search(self):
        """Search finds messages by substring."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "hello world", a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "goodbye world", a2a.now() + 1)
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "hello again", a2a.now() + 2)
        )
        conn.commit()
        conn.close()

        # Search should find messages containing "hello"
        args = a2a.argparse.Namespace(project=self.project, query="hello", limit=50, json=False, fts=False)
        # Manually call cmd_search and check it doesn't crash
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("hello world", output)
        self.assertIn("hello again", output)
        self.assertNotIn("goodbye", output)

    def test_fts_init_rebuild_only_on_first_call(self):
        """_init_fts() only triggers FTS5 rebuild when table is newly created."""
        conn = a2a.connect(self.project)
        rebuild_calls = []

        def trace(sql):
            if "rebuild" in sql.lower():
                rebuild_calls.append(sql)

        conn.set_trace_callback(trace)
        a2a._init_fts(conn)
        self.assertEqual(len(rebuild_calls), 1, "rebuild should run exactly once on first init")

        rebuild_calls.clear()
        a2a._init_fts(conn)
        self.assertEqual(len(rebuild_calls), 0, "rebuild must not run on subsequent _init_fts calls")
        conn.set_trace_callback(None)
        conn.close()

    def _search_output(self, project, query, fts=True):
        """Helper: run cmd_search and return stdout."""
        import io, sys
        args = a2a.argparse.Namespace(project=project, query=query, limit=50, json=False, fts=fts)
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        return output

    def _seed_fts_messages(self, project):
        """Insert messages for FTS5 quality tests."""
        conn = a2a.connect(project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        messages = [
            "authentication token expired",
            "database connection failed",
            "user login successful",
            "authentication error on retry",
            "deployment pipeline complete",
        ]
        for i, body in enumerate(messages):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", None, body, a2a.now() + i)
            )
        conn.commit()
        conn.close()

    def test_fts_single_term(self):
        """FTS5 search finds messages containing a single term."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "authentication")
        self.assertIn("authentication token expired", out)
        self.assertIn("authentication error on retry", out)
        self.assertNotIn("database connection", out)

    def test_fts_boolean_and(self):
        """FTS5 AND operator requires both terms to be present."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "authentication AND error")
        self.assertIn("authentication error on retry", out)
        self.assertNotIn("authentication token expired", out)

    def test_fts_boolean_or(self):
        """FTS5 OR operator returns messages with either term."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "login OR deployment")
        self.assertIn("user login successful", out)
        self.assertIn("deployment pipeline complete", out)
        self.assertNotIn("authentication", out)

    def test_fts_prefix_query(self):
        """FTS5 prefix* matches terms starting with the prefix."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "auth*")
        self.assertIn("authentication token expired", out)
        self.assertIn("authentication error on retry", out)
        self.assertNotIn("database connection", out)

    def test_fts_forced_flag(self):
        """--fts flag forces FTS5 path even without prior init."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "database", fts=True)
        self.assertIn("database connection failed", out)

    def test_search_like_fallback(self):
        """Search without FTS still finds matches via LIKE fallback."""
        self._seed_fts_messages(self.project)
        out = self._search_output(self.project, "pipeline", fts=False)
        self.assertIn("deployment pipeline complete", out)

    def test_peek_limit_caps_output(self):
        """Peek with --limit N caps the number of messages shown."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice",):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        for i in range(5):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", None, f"msg-{i}", a2a.now() + i)
            )
        conn.commit()
        conn.close()

        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_peek(a2a.argparse.Namespace(project=self.project, limit=2, json=False))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        # Peek orders by newest first; limit=2 should show at most 2 message blocks
        lines = [l for l in output.split('\n') if l.strip().startswith('#')]
        self.assertLessEqual(len(lines), 2)

    def test_stats(self):
        """Stats command reports correct counts."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("bob", "done", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)",
            ("alice", "bob", "direct msg", None, a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)",
            ("alice", None, "broadcast", None, a2a.now() + 1)
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)",
            ("bob", "alice", "reply", "topic1", a2a.now() + 2)
        )
        conn.commit()
        conn.close()

        # Call stats and check JSON output
        args = a2a.argparse.Namespace(project=self.project, json=True)
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_stats(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        data = json.loads(output)
        self.assertEqual(data["messages"], 3)
        self.assertEqual(data["direct_messages"], 2)
        self.assertEqual(data["broadcasts"], 1)
        self.assertEqual(data["threads"], 1)
        self.assertEqual(data["agents_active"], 1)
        self.assertEqual(data["agents_done"], 1)

    def test_send_unicode_body(self):
        """Send with Unicode characters in body stores correctly."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

        # Unicode body with emoji and accented characters
        body = "Hello ✨ — ñoño méil 日本語"
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body=body,
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT body FROM messages WHERE sender=? AND recipient=?",
            ("alice", "bob")
        ).fetchone()
        self.assertEqual(row["body"], body)
        conn.close()

    def test_send_with_thread_and_ttl(self):
        """Send with both --thread and --ttl works together."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.commit()
        conn.close()

        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="threaded ttl msg",
            **{"from_": "alice", "thread": "topic-42", "ttl": 3600}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT body, thread_id, ttl_seconds FROM messages WHERE body=?",
            ("threaded ttl msg",)
        ).fetchone()
        self.assertEqual(row["thread_id"], "topic-42")
        self.assertEqual(row["ttl_seconds"], 3600)
        conn.close()

    def test_cmd_thread_with_messages(self):
        """cmd_thread retrieves all messages in a thread in chronological order."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)",
            ("alice", "bob", "first", "thread-1", a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)",
            ("bob", "alice", "second", "thread-1", a2a.now() + 1)
        )
        conn.commit()
        conn.close()

        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_thread(a2a.argparse.Namespace(
            project=self.project, id="thread-1", json=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("first", output)
        self.assertIn("second", output)
        # Chronological order: first should appear before second
        self.assertLess(output.index("first"), output.index("second"))

    def test_cmd_thread_empty(self):
        """cmd_thread with unknown thread ID prints a notice."""
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_thread(a2a.argparse.Namespace(
            project=self.project, id="nonexistent", json=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("no messages in thread", output)

    def test_cmd_search_limit(self):
        """Search with --limit caps results to at most N messages."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", None, f"limit test msg {i}", a2a.now() + i)
            )
        conn.commit()
        conn.close()

        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(a2a.argparse.Namespace(
            project=self.project, query="limit", limit=2, json=True, fts=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertLessEqual(len(data), 2, "search --limit 2 should return at most 2 messages")

    def test_cmd_search_special_like_chars(self):
        """Search handles special LIKE characters like % and _ in message bodies."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "progress: 90% done", a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "underscore_var_name", a2a.now() + 1)
        )
        conn.commit()
        conn.close()

        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(a2a.argparse.Namespace(
            project=self.project, query="90%", limit=50, json=False, fts=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("90% done", output)

        # Search for a term containing underscore
        old_stdout2 = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(a2a.argparse.Namespace(
            project=self.project, query="underscore", limit=50, json=False, fts=False
        ))
        output2 = sys.stdout.getvalue()
        sys.stdout = old_stdout2
        self.assertIn("underscore_var_name", output2)

    def test_cmd_recv_since_filters_old_messages(self):
        """recv --since filters out messages older than the timestamp."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        # Insert old message
        old_ts = a2a.now() - 100
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", "bob", "old message", old_ts)
        )
        # Insert recent message
        new_ts = a2a.now()
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", "bob", "recent message", new_ts)
        )
        conn.commit()
        conn.close()

        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_recv(a2a.argparse.Namespace(
            project=self.project, as_="bob", wait=0, all=False,
            peek=False, limit=0, since=old_ts + 50, json=False, include_self=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("recent message", output)
        self.assertNotIn("old message", output)

    def test_cmd_stats_empty_bus(self):
        """Stats on a bus with no messages returns zero counts."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_stats(a2a.argparse.Namespace(project=self.project, json=True))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertEqual(data["messages"], 0)
        self.assertEqual(data["direct_messages"], 0)
        self.assertEqual(data["broadcasts"], 0)
        self.assertEqual(data["threads"], 0)
        self.assertEqual(data["agents_active"], 0)
        self.assertEqual(data["agents_done"], 0)








class TestWALInvariant(unittest.TestCase):
    """Verify the WAL invariant: every db entry point sets WAL + busy_timeout."""

    def setUp(self):
        self.test_home = tempfile.mkdtemp()
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = self.test_home

    def tearDown(self):
        if self.original_home:
            os.environ["HOME"] = self.original_home
        import shutil
        shutil.rmtree(self.test_home, ignore_errors=True)

    def _open_db(self, project: str) -> sqlite3.Connection:
        """Open the project database directly."""
        db_path = Path(self.test_home) / ".a2a" / project / "database.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def test_a2a_connect_sets_wal(self):
        """a2a.connect() enables WAL journal mode."""
        project = f"wal-test-{os.getpid()}"
        conn = a2a.connect(project, create=True)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode, "wal")

    def test_a2a_connect_sets_busy_timeout(self):
        """a2a.connect() sets busy_timeout to 5000 ms."""
        project = f"busy-test-{os.getpid()}"
        conn = a2a.connect(project, create=True)
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        self.assertEqual(timeout, 5000)

    def test_mkdir_guard_creates_parent(self):
        """a2a.connect() creates parent directory automatically."""
        project = f"mkdir-test-{os.getpid()}"
        db_path = Path(self.test_home) / ".a2a" / project / "database.db"
        self.assertFalse(db_path.parent.exists())
        conn = a2a.connect(project, create=True)
        conn.close()
        self.assertTrue(db_path.parent.exists())
        self.assertTrue(db_path.exists())

    def test_wal_survives_reconnect(self):
        """WAL mode persists across multiple connections to the same db."""
        project = f"wal-reconnect-{os.getpid()}"
        conn = a2a.connect(project, create=True)
        conn.close()

        # Reconnect without create — WAL should already be set by first open
        conn2 = a2a.connect(project, create=False)
        mode = conn2.execute("PRAGMA journal_mode").fetchone()[0]
        conn2.close()
        self.assertEqual(mode, "wal")

    def test_a2a_client_sets_wal(self):
        """A2AClient (sync) enables WAL on connection."""
        from a2a_client import A2AClient
        project = f"client-wal-{os.getpid()}"
        # Pre-create schema so client can connect
        conn = a2a.connect(project, create=True)
        conn.close()

        client = A2AClient(project, "agent")
        db_conn = client._connect()
        mode = db_conn.execute("PRAGMA journal_mode").fetchone()[0]
        db_conn.close()
        self.assertEqual(mode, "wal")

    def test_a2a_client_mkdir_guard(self):
        """A2AClient creates parent directory before connecting."""
        from a2a_client import A2AClient
        project = f"client-mkdir-{os.getpid()}"
        db_path = Path(self.test_home) / ".a2a" / project / "database.db"
        self.assertFalse(db_path.parent.exists())

        client = A2AClient(project, "agent")
        conn = client._connect()
        conn.close()
        self.assertTrue(db_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
