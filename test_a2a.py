#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for a2a.py — peer messaging CLI.

Covers: DB schema, message send/recv, read-tracking, filtering, edge cases.
Run: python3 test_a2a.py
"""
from test_helpers import make_connection
import json
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

    def test_init_idempotent(self):
        """Calling init on an already-initialized project does not drop tables or error."""
        conn1 = a2a.connect(self.project, create=True)
        conn1.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn1.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "data before re-init", a2a.now())
        )
        conn1.commit()
        conn1.close()

        # Call init again via connect(create=True) — should not drop data
        conn2 = a2a.connect(self.project, create=True)
        tables = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        self.assertIn("agents", names)
        self.assertIn("messages", names)

        # Data should still be there
        row = conn2.execute(
            "SELECT body FROM messages WHERE body='data before re-init'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["body"], "data before re-init")
        conn2.close()


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

    def test_register_with_pid(self):
        """Register with --pid stores the pid in the database."""
        args = a2a.argparse.Namespace(
            project=self.project, id="pid-agent", role="worker",
            prompt="", cli="opencode", pid=12345, upsert=False
        )
        a2a.cmd_register(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT pid FROM agents WHERE id=?", ("pid-agent",)).fetchone()
        conn.close()
        self.assertEqual(row["pid"], 12345)

    def test_register_upsert_updates_pid(self):
        """Upsert with explicit pid updates the stored pid."""
        args = a2a.argparse.Namespace(
            project=self.project, id="pid-update", role="worker",
            prompt="", cli="opencode", pid=100, upsert=False
        )
        a2a.cmd_register(args)
        args.pid = 200
        args.upsert = True
        a2a.cmd_register(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT pid FROM agents WHERE id=?", ("pid-update",)).fetchone()
        conn.close()
        self.assertEqual(row["pid"], 200)


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
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, **{"as_": "bob", "wait": 0, "all": False,
                                         "peek": False, "limit": 0, "since": None,
                                         "json": False, "include_self": False}
            )
            a2a.cmd_recv(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("msg1", output)
        self.assertIn("broadcast", output)

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
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, **{"as_": "bob", "wait": 0, "all": True,
                                         "peek": False, "limit": 0, "since": None,
                                         "json": False, "include_self": False}
            )
            a2a.cmd_recv(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("old msg", output)

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

        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice", "wait": 0, "all": False,
                                         "peek": False, "limit": 0, "since": None,
                                         "json": False, "include_self": False}
            )
            a2a.cmd_recv(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        # Self-sent msg should NOT appear without --include-self
        self.assertNotIn("self message", output)

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

        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice", "wait": 0, "all": False,
                                         "peek": False, "limit": 0, "since": None,
                                         "json": False, "include_self": True}
            )
            a2a.cmd_recv(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        # Self-sent msg SHOULD appear with --include-self
        self.assertIn("self message", output)


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

    def test_status_json_output(self):
        """cmd_status --json returns valid JSON with expected fields."""
        self._register("json-tester")
        import io, sys, json
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            a2a.cmd_status(a2a.argparse.Namespace(
                project=self.project, state="done", **{"as_": "json-tester"},
                json=True,
            ))
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        data = json.loads(output)
        self.assertEqual(data["agent"], "json-tester")
        self.assertEqual(data["status"], "done")
        self.assertIn("last_seen", data)

    def test_status_unknown_agent(self):
        """Status on unknown agent fails gracefully."""
        args = a2a.argparse.Namespace(
            project=self.project, state="done", **{"as_": "nobody"}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_status(args)

    def test_status_invalid_value(self):
        """Status with invalid value is rejected."""
        self._register("tester")
        for bad_state in ("invalid", "abc", "unknown", "running", ""):
            args = a2a.argparse.Namespace(
                project=self.project, state=bad_state, **{"as_": "tester"}
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
        """List agents outputs valid JSON with correct agent data."""
        self._register("agent-a", role="dev")
        self._register("agent-b", role="critic")
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_list(a2a.argparse.Namespace(project=self.project, json=True))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        ids = {d["id"] for d in data}
        self.assertIn("agent-a", ids)
        self.assertIn("agent-b", ids)

    def test_list_agents_json_empty(self):
        """List --json on empty bus returns valid JSON empty array."""
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_list(a2a.argparse.Namespace(project=self.project, json=True))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_list_agents_empty(self):
        """List on empty bus prints '(no agents registered)'."""
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(project=self.project, json=False)
            a2a.cmd_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("no agents registered", output)

    def test_project_info(self):
        """Project command prints resolved project info."""
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(project=self.project)
            a2a.cmd_project(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        info = json.loads(output)
        self.assertEqual(info["project"], self.project)
        self.assertIn("database.db", info["db"])
        self.assertIsInstance(info["exists"], bool)

    def test_cmd_list_no_database(self):
        """List on non-initialized project raises SystemExit (connect fails)."""
        project = f"list-nonex-{os.getpid()}"
        with self.assertRaises(SystemExit):
            a2a.cmd_list(a2a.argparse.Namespace(project=project, json=False))

    def test_cmd_clear_no_database(self):
        """Clear on a project with no database prints notice and does not crash."""
        project = f"clear-nonex-{os.getpid()}"
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_clear(a2a.argparse.Namespace(project=project, yes=True))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("nothing to clear", output)

    def test_cmd_clear_refuses_without_yes(self):
        """Clear without --yes exits with error."""
        with self.assertRaises(SystemExit):
            a2a.cmd_clear(
                a2a.argparse.Namespace(project=self.project, yes=False)
            )

    def test_cmd_clear_with_yes_removes_database(self):
        """Clear --yes removes the database file."""
        project = f"clear-test-{os.getpid()}"
        a2a.connect(project, create=True).close()
        db = a2a.db_path(project)
        self.assertTrue(db.exists(), "DB should exist before clear")
        a2a.cmd_clear(a2a.argparse.Namespace(project=project, yes=True))
        self.assertFalse(db.exists(), "DB should be removed after clear")


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

    def test_send_unknown_sender(self):
        """Sending from an unregistered agent fails gracefully."""
        # Register recipient but not sender
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="hi",
            **{"from_": "unregistered-sender", "thread": None}
        )
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
    def test_cmd_send_thread_id_too_long_raises_error(self):
        """Send with --thread > 256 chars raises SystemExit."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("bob", "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()
        with self.assertRaises(SystemExit):
            a2a.cmd_send(a2a.argparse.Namespace(
                project=self.project, to="bob", body="test",
                **{"from_": "alice", "thread": "t" * 300, "ttl": None, "json": False}
            ))

    def test_cmd_send_body_too_long_raises_error(self):
        """Send with body > 100000 chars raises SystemExit."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("bob", "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()
        long_body = "x" * 100_001
        with self.assertRaises(SystemExit):
            a2a.cmd_send(a2a.argparse.Namespace(
                project=self.project, to="bob", body=long_body,
                **{"from_": "alice", "thread": None, "ttl": None, "json": False}
            ))


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

    def test_cmd_thread_id_too_long_raises_error(self):
        """cmd_thread with thread ID > 256 chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_thread(a2a.argparse.Namespace(
                project=self.project, id="t" * 300, json=False
            ))

    def test_cmd_thread_whitespace_id_raises_error(self):
        """cmd_thread with whitespace-only thread ID raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_thread(a2a.argparse.Namespace(
                project=self.project, id="   ", json=False
            ))

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

    def test_cmd_wait_unknown_agent(self):
        """cmd_wait with unknown agent exits with error."""
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="phantom", timeout=0, count=1
            ))

    def test_cmd_wait_zero_count(self):
        """cmd_wait with --count 0 is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice", timeout=0, count=0
            ))

    def test_cmd_wait_negative_count(self):
        """cmd_wait with negative --count is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice", timeout=0, count=-1
            ))

    def test_cmd_wait_negative_timeout(self):
        """cmd_wait with negative --timeout is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice", timeout=-1, count=1
            ))

    def test_cmd_wait_timeout_no_messages(self):
        """cmd_wait with no unread messages and zero timeout exits with error."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()
        with self.assertRaises(SystemExit) as cm:
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice", timeout=0, count=1
            ))
        self.assertEqual(cm.exception.code, 2)

    def test_cmd_wait_immediate_success(self):
        """cmd_wait returns immediately if count is already met."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", "alice", "ready message", a2a.now())
        )
        conn.commit()
        conn.close()
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_wait(a2a.argparse.Namespace(
            project=self.project, as_="alice", timeout=0, count=1
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("ok: 1 unread", output)

    def test_cmd_send_empty_body(self):
        """Send with empty body works at CLI level (creates message with empty content)."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT body FROM messages WHERE sender='alice'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["body"], "")

    def test_cmd_recv_since_and_limit(self):
        """recv with both --since and --limit filters by time then caps results."""
        self._register("alice")
        self._register("bob")
        conn = a2a.connect(self.project)
        # Send 3 messages at different timestamps (id is INTEGER PK)
        for i, body in enumerate(["first", "second", "third"]):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("bob", "alice", body, float(1000 + i)),
            )
        conn.commit()
        conn.close()
        # recv with since=1000.5 and limit=1 should return only "second"
        args = a2a.argparse.Namespace(
            project=self.project, **{"as_": "alice", "wait": 0, "limit": 1,
                                     "since": 1000.5, "all": True, "peek": False,
                                     "json": False, "include_self": False}
        )
        a2a.cmd_recv(args)
        # Verify by querying the reads table — only 1 message should have been returned
        conn = a2a.connect(self.project)
        read_ids = [r["message_id"] for r in
                    conn.execute("SELECT message_id FROM reads WHERE agent_id='alice' ORDER BY message_id").fetchall()]
        conn.close()
        self.assertEqual(len(read_ids), 1)

    def test_cmd_project_json_output(self):
        """cmd_project outputs valid JSON with expected structure."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        args = a2a.argparse.Namespace(project=self.project)
        a2a.cmd_project(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIn("project", data)
        self.assertIn("db", data)
        self.assertIn("exists", data)
        self.assertEqual(data["project"], self.project)
        self.assertIsInstance(data["exists"], bool)

    def test_cross_project_recv_isolation(self):
        """Recv in project A should not see messages from project B, even if both have same agent name."""
        project_a = f"{self.project}-a"
        project_b = f"{self.project}-b"
        a2a.connect(project_a, create=True).close()
        a2a.connect(project_b, create=True).close()

        def register_in_project(p, agent_id):
            conn = a2a.connect(p)
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
            conn.commit()
            conn.close()

        # Register two agents in each project
        register_in_project(project_a, "alice")
        register_in_project(project_a, "bob")
        register_in_project(project_b, "alice")
        register_in_project(project_b, "bob")

        # Send a message from bob to alice in project_a
        args_send = a2a.argparse.Namespace(
            project=project_a, to="alice", body="secret-project-a",
            **{"from_": "bob", "thread": None}
        )
        a2a.cmd_send(args_send)

        # Recv in project_a should get it
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_recv(a2a.argparse.Namespace(
            project=project_a, as_="alice", wait=0, all=True,
            peek=False, limit=None, since=None, json=True, include_self=False
        ))
        output_a = sys.stdout.getvalue()
        sys.stdout = old_stdout

        # Recv in project_b should NOT get it
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_recv(a2a.argparse.Namespace(
            project=project_b, as_="alice", wait=0, all=True,
            peek=False, limit=None, since=None, json=True, include_self=False
        ))
        output_b = sys.stdout.getvalue()
        sys.stdout = old_stdout

        data_a = json.loads(output_a) if output_a.strip() else []
        data_b = json.loads(output_b) if output_b.strip() else []
        bodies_a = [m["body"] for m in data_a]
        bodies_b = [m["body"] for m in data_b]
        self.assertIn("secret-project-a", bodies_a, "project A should have the message")
        self.assertNotIn("secret-project-a", bodies_b, "project B should NOT see project A's messages")

        # Cleanup
        for p in (a2a.db_path(project_a), a2a.db_path(project_b)):
            if p.exists():
                p.unlink()

    def test_cmd_send_stdin_body(self):
        """cmd_send with '-' body reads from stdin."""
        self._register("alice")
        self._register("bob")
        import io, sys
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("stdin body content")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="-",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        sys.stdin = old_stdin
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT body FROM messages WHERE sender='alice'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["body"], "stdin body content")

    def test_cmd_send_json_output(self):
        """cmd_send --json produces valid JSON with expected fields."""
        self._register("alice")
        self._register("bob")
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_send(a2a.argparse.Namespace(
                project=self.project, to="bob", body="hello",
                **{"from_": "alice", "thread": None, "json": True}
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output.strip())
        self.assertIn("id", data)
        self.assertIn("sender", data)
        self.assertIn("recipient", data)
        self.assertEqual(data["sender"], "alice")
        self.assertEqual(data["recipient"], "bob")
        self.assertIsInstance(data["id"], int)

    def test_cmd_send_json_output_broadcast(self):
        """cmd_send --json to 'all' shows recipient as 'ALL'."""
        self._register("alice")
        self._register("bob")
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_send(a2a.argparse.Namespace(
                project=self.project, to="all", body="broadcast test",
                **{"from_": "alice", "thread": None, "json": True}
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output.strip())
        self.assertEqual(data["sender"], "alice")
        self.assertEqual(data["recipient"], "ALL")
        self.assertIsInstance(data["id"], int)

    def test_cmd_peek_negative_limit_rejected(self):
        """Negative --limit is rejected."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.commit()
        conn.close()

        with self.assertRaises(SystemExit):
            a2a.cmd_peek(a2a.argparse.Namespace(
                project=self.project, limit=-1, json=True
            ))

    def test_cmd_wait_ignores_expired_messages(self):
        """cmd_wait does not count TTL-expired messages as unread."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        # Insert an already-expired message
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            ("bob", "alice", "expired msg", 1, a2a.now() - 10)
        )
        conn.commit()
        conn.close()

        with self.assertRaises(SystemExit) as cm:
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice", timeout=0, count=1
            ))
        self.assertEqual(cm.exception.code, 2,
                         "expired messages should not count toward wait")

    def test_validate_finite_float_nan(self):
        """_validate_finite_float rejects NaN."""
        with self.assertRaises(SystemExit):
            a2a._validate_finite_float(float("nan"), "test_param")

    def test_validate_finite_float_inf(self):
        """_validate_finite_float rejects infinity."""
        with self.assertRaises(SystemExit):
            a2a._validate_finite_float(float("inf"), "test_param")
        with self.assertRaises(SystemExit):
            a2a._validate_finite_float(float("-inf"), "test_param")

    def test_validate_finite_float_none(self):
        """_validate_finite_float allows None (optional param not provided)."""
        try:
            a2a._validate_finite_float(None, "optional_param")
        except SystemExit:
            self.fail("_validate_finite_float raised SystemExit for None")

    def test_validate_finite_float_valid(self):
        """_validate_finite_float allows valid finite floats."""
        try:
            a2a._validate_finite_float(0.0, "param")
            a2a._validate_finite_float(30.5, "param")
            a2a._validate_finite_float(-1.0, "param")
        except SystemExit:
            self.fail("_validate_finite_float raised SystemExit for valid float")

    def test_cmd_stats_json_empty(self):
        """cmd_stats --json on empty bus returns valid JSON with zero counts."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        args = a2a.argparse.Namespace(project=self.project, json=True)
        a2a.cmd_stats(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertEqual(data["messages"], 0)
        self.assertEqual(data["agents_active"], 0)
        self.assertEqual(data["agents_done"], 0)
        self.assertEqual(data["top_senders"], [])

    def test_cmd_peek_json_output(self):
        """cmd_peek --json outputs valid JSON array."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="peek me",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        args = a2a.argparse.Namespace(project=self.project, limit=10, json=True)
        a2a.cmd_peek(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("body", data[0])
        self.assertIn("sender", data[0])
        self.assertEqual(data[0]["body"], "peek me")

    def test_cmd_peek_json_empty_bus(self):
        """cmd_peek --json on empty bus returns empty JSON array."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_peek(a2a.argparse.Namespace(
                project=self.project, limit=10, json=True
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_cmd_search_fts_force(self):
        """cmd_search --fts --json produces valid JSON results."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="unique-fts-search-term",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        args = a2a.argparse.Namespace(
            project=self.project, query="unique-fts-search-term",
            limit=50, json=True, fts=True
        )
        a2a.cmd_search(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("body", data[0])
        self.assertEqual(data[0]["body"], "unique-fts-search-term")

    def test_cmd_send_ttl_non_positive_rejected(self):
        """cmd_send with --ttl 0 or negative is rejected."""
        self._register("alice")
        self._register("bob")
        for bad_ttl in (0, -1, -5):
            args = a2a.argparse.Namespace(
                project=self.project, to="bob", body=f"ttl-{bad_ttl}-msg",
                **{"from_": "alice", "thread": None, "ttl": bad_ttl}
            )
            with self.assertRaises(SystemExit):
                a2a.cmd_send(args)
        # Verify no messages with non-positive TTL were stored
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE body LIKE 'ttl-%'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(row, 0, "no messages with non-positive TTL should be stored")

    def test_register_then_upsert_changes_role(self):
        """Register agent then upsert with different role updates stored fields."""
        self._register("morph")
        args = a2a.argparse.Namespace(
            project=self.project, id="morph", role="builder",
            prompt="initial", cli="claude", pid=None, upsert=True
        )
        a2a.cmd_register(args)
        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT role, prompt, cli FROM agents WHERE id='morph'"
        ).fetchone()
        conn.close()
        self.assertEqual(row["role"], "builder")
        self.assertEqual(row["prompt"], "initial")
        self.assertEqual(row["cli"], "claude")

    def test_cmd_unregister_nonexistent_agent(self):
        """Unregistering a non-existent agent prints removed 0 and does not crash."""
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_unregister(
                a2a.argparse.Namespace(project=self.project, id="phantom")
            )
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("removed 0", output)

    def test_cmd_register_empty_id_raises_error(self):
        """Register with empty agent ID prints error and exits."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="", role="tester",
                    prompt="", cli="", pid=0, upsert=False,
                )
            )

    def test_cmd_register_whitespace_id_raises_error(self):
        """Register with whitespace-only agent ID prints error and exits."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="   ", role="tester",
                    prompt="", cli="", pid=0, upsert=False,
                )
            )

    def test_cmd_unregister_empty_id_raises_error(self):
        """Unregister with empty agent ID prints error and exits."""
        with self.assertRaises(SystemExit):
            a2a.cmd_unregister(
                a2a.argparse.Namespace(project=self.project, id="")
            )

    def test_cmd_unregister_whitespace_id_raises_error(self):
        """Unregister with whitespace-only agent ID prints error and exits."""
        with self.assertRaises(SystemExit):
            a2a.cmd_unregister(
                a2a.argparse.Namespace(project=self.project, id="   ")
            )

    def test_cmd_list_empty_bus(self):
        """List on a bus with no registered agents shows a notice."""
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_list(
                a2a.argparse.Namespace(project=self.project, json=False)
            )
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("no agents registered", output.lower())

    def test_cmd_recv_include_self(self):
        """recv --include-self returns own messages."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="alice", body="self message",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        import io, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice", "wait": 0,
                                         "all": True, "peek": False,
                                         "limit": 0, "since": None,
                                         "json": True, "include_self": True}
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output) if output.strip() else []
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("self message", [m["body"] for m in data])

    def test_search_empty_query(self):
        """Search with empty query is rejected."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "findable message", a2a.now())
        )
        conn.commit()
        conn.close()

        with self.assertRaises(SystemExit):
            a2a.cmd_search(a2a.argparse.Namespace(
                project=self.project, query="", limit=50, json=False, fts=False
            ))

    def test_search_whitespace_query_rejected(self):
        """Search with whitespace-only query is rejected."""
        with self.assertRaises(SystemExit):
            a2a.cmd_search(a2a.argparse.Namespace(
                project=self.project, query="   ", limit=50, json=False, fts=False
            ))

    def test_search_no_matches(self):
        """Search with query that matches nothing returns empty cleanly."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "hello", a2a.now())
        )
        conn.commit()
        conn.close()

        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(a2a.argparse.Namespace(
            project=self.project, query="zzznonexistent", limit=50, json=True, fts=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        # With --json and no matches, should output valid JSON (either [] or notice)
        try:
            data = json.loads(output) if output.strip() else []
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 0)
        except json.JSONDecodeError:
            # Accept human-readable notice as fallback
            self.assertIn("no messages", output.lower())

    def test_message_ordering_identical_timestamps(self):
        """Messages with the same created_at are ordered by ID (insertion order)."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        ts = a2a.now()
        for i, body in enumerate(["msg-c", "msg-a", "msg-b"]):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", None, body, ts),
            )
        conn.commit()
        conn.close()

        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_peek(a2a.argparse.Namespace(project=self.project, limit=10, json=True))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output) if output.strip() else []
        # peek with id=json output: ORDER BY created_at DESC then reversed, so it's ASC
        # With same timestamp, fallback is autoincrement id ascending
        bodies = [m["body"] for m in data]
        # "msg-c" inserted first (id=1), "msg-a" second (id=2), "msg-b" third (id=3)
        self.assertEqual(bodies, ["msg-c", "msg-a", "msg-b"],
                         "Messages with same timestamp should be ordered by ID (insertion order)")

    def test_recv_reads_table_updated(self):
        """recv creates read-tracking entries for delivered messages."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", "bob", "msg for bob", a2a.now())
        )
        conn.commit()
        conn.close()

        # recv as bob
        args = a2a.argparse.Namespace(
            project=self.project, as_="bob", wait=0,
            all=False, include_self=False, peek=False,
            since=None, limit=None, json=True
        )
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_recv(args)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        # Verify reads table has an entry for bob
        conn = a2a.connect(self.project)
        read_count = conn.execute(
            "SELECT COUNT(*) FROM reads WHERE agent_id='bob'"
        ).fetchone()[0]
        conn.close()
        self.assertGreaterEqual(read_count, 1, "recv should create read-tracking entry")

    def test_upsert_preserves_unset_fields(self):
        """upsert updates only specified fields, leaves others intact."""
        # Register with all fields
        args = a2a.argparse.Namespace(
            project=self.project, id="multi", role="original_role",
            prompt="original_prompt", cli="original_cli", pid=42, upsert=False
        )
        a2a.cmd_register(args)

        # Upsert with only a new role
        args2 = a2a.argparse.Namespace(
            project=self.project, id="multi", role="new_role",
            prompt=None, cli=None, pid=None, upsert=True
        )
        a2a.cmd_register(args2)

        conn = a2a.connect(self.project)
        row = conn.execute(
            "SELECT role, prompt, cli, pid FROM agents WHERE id='multi'"
        ).fetchone()
        conn.close()
        self.assertEqual(row["role"], "new_role", "role should be updated")
        self.assertEqual(row["prompt"], "original_prompt", "prompt should be preserved")
        self.assertEqual(row["cli"], "original_cli", "cli should be preserved")
        self.assertEqual(row["pid"], 42, "pid should be preserved")

    def test_peek_returns_newest_first(self):
        """peek returns messages in reverse chronological order (newest first) in non-JSON, chronological in JSON."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        base_ts = a2a.now()
        for i in range(3):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", None, f"msg-{i}", base_ts + i)
            )
        conn.commit()
        conn.close()

        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_peek(a2a.argparse.Namespace(project=self.project, limit=10, json=True))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        data = json.loads(output) if output.strip() else []
        bodies = [m["body"] for m in data]
        # JSON peek order: oldest first (chronological)
        self.assertEqual(bodies, ["msg-0", "msg-1", "msg-2"],
                         "peek JSON output should be chronological order")

    def test_recv_negative_wait_returns_immediately(self):
        """recv with negative --wait returns immediately (no block)."""
        self._register("alice")
        self._register("bob")
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_="bob", wait=-5, all=True,
                peek=False, limit=None, since=None, json=True, include_self=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        # Should not crash; negative wait means deadline is already in the past
        data = json.loads(output) if output.strip() else []
        self.assertIsInstance(data, list)

    def test_peek_limit_non_positive_rejected(self):
        """peek with --limit 0 or negative is rejected."""
        self._register("alice")
        args = a2a.argparse.Namespace(
            project=self.project, to="alice", body="visible?",
            **{"from_": "alice", "thread": None}
        )
        a2a.cmd_send(args)
        for bad_limit in (0, -1):
            with self.assertRaises(SystemExit):
                a2a.cmd_peek(a2a.argparse.Namespace(
                    project=self.project, limit=bad_limit, json=True))

    def test_send_without_from_raises_error(self):
        """send without --from raises SystemExit."""
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="missing sender",
            **{"from_": None, "thread": None}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_send(args)

    def test_search_invalid_fts_falls_back(self):
        """Search with invalid FTS syntax falls back gracefully to LIKE."""
        self._register("alice")
        conn = a2a.connect(self.project)
        # Create a message
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "test content here", a2a.now())
        )
        conn.commit()
        conn.close()
        # Use NEAR() which has bad syntax — FTS5 should error and fall back to LIKE
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_search(a2a.argparse.Namespace(
                project=self.project, query='NEAR(content)', limit=50,
                json=False, fts=True
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("test content", output)

    def test_search_limit_non_positive_rejected(self):
        """search with --limit 0 or negative is rejected."""
        self._register("alice")
        for bad_limit in (0, -1):
            with self.assertRaises(SystemExit):
                a2a.cmd_search(a2a.argparse.Namespace(
                    project=self.project, query="test", limit=bad_limit,
                    json=False, fts=False
                ))

    def test_recv_limit_negative_rejected(self):
        """recv with negative --limit is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice"},
                wait=0, limit=-1, all=False, since=None,
                include_self=False, peek=False, json=False
            ))

    def test_send_empty_recipient_rejected(self):
        """send with empty recipient is rejected."""
        args = a2a.argparse.Namespace(
            project=self.project, to="", body="hi",
            **{"from_": "alice", "thread": None}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_send(args)

    def test_send_whitespace_recipient_rejected(self):
        """send with whitespace-only recipient is rejected."""
        args = a2a.argparse.Namespace(
            project=self.project, to="   ", body="hi",
            **{"from_": "alice", "thread": None}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_send(args)

    def test_send_empty_thread_rejected(self):
        """send with --thread '' is rejected."""
        self._register("alice")
        self._register("bob")
        args = a2a.argparse.Namespace(
            project=self.project, to="bob", body="msg",
            **{"from_": "alice", "thread": ""}
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_send(args)

    def test_recv_negative_since_rejected(self):
        """recv with --since -1 is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice"},
                wait=0, limit=10, all=False, since=-1,
                include_self=False, peek=False, json=False
            ))

    def test_register_negative_pid_rejected(self):
        """register with --pid -1 is rejected."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(a2a.argparse.Namespace(
                project=self.project, id="test-agent",
                role="test", prompt=None, cli=None,
                pid=-1, upsert=False
            ))

    def test_recv_nan_wait_rejected(self):
        """recv with --wait NaN is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice"},
                wait=float("nan"), limit=0, all=False, since=None,
                include_self=False, peek=False, json=False
            ))

    def test_recv_inf_wait_rejected(self):
        """recv with --wait inf is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice"},
                wait=float("inf"), limit=0, all=False, since=None,
                include_self=False, peek=False, json=False
            ))

    def test_recv_nan_since_rejected(self):
        """recv with --since NaN is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, **{"as_": "alice"},
                wait=0, limit=0, all=False, since=float("nan"),
                include_self=False, peek=False, json=False
            ))

    def test_wait_nan_timeout_rejected(self):
        """cmd_wait with --timeout NaN is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice",
                timeout=float("nan"), count=1
            ))

    def test_wait_inf_timeout_rejected(self):
        """cmd_wait with --timeout inf is rejected."""
        self._register("alice")
        with self.assertRaises(SystemExit):
            a2a.cmd_wait(a2a.argparse.Namespace(
                project=self.project, as_="alice",
                timeout=float("inf"), count=1
            ))

    def test_peek_limit_capped_at_1000(self):
        """peek with --limit > 1000 is capped to 1000, not rejected."""
        conn = a2a.connect(self.project, create=True)
        for i in range(5):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (f"agent{i}", "active", a2a.now(), a2a.now())
            )
            conn.execute(
                "INSERT INTO messages(sender, body, created_at) VALUES (?,?,?)",
                (f"agent{i}", f"message {i}", a2a.now())
            )
        conn.commit()
        conn.close()
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_peek(a2a.argparse.Namespace(
            project=self.project, limit=9999, json=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        # Should only show up to 1000 messages (we only have 5)
        self.assertIn("message 0", output)

    def test_search_limit_capped_at_200(self):
        """search with --limit > 200 is capped to 200."""
        conn = a2a.connect(self.project, create=True)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        for i in range(10):
            conn.execute(
                "INSERT INTO messages(sender, body, created_at) VALUES (?,?,?)",
                ("alice", f"searchable message {i}", a2a.now())
            )
        conn.commit()
        conn.close()
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        a2a.cmd_search(a2a.argparse.Namespace(
            project=self.project, query="searchable",
            limit=999, json=False, fts=False
        ))
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        # Should find all 10 messages (well under 200 cap)
        self.assertIn("searchable message 9", output)

    def test_cmd_register_id_too_long_raises_error(self):
        """Register with agent ID > 256 chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="a" * 300, role="tester",
                    prompt="", cli="", pid=0, upsert=False,
                )
            )

    def test_cmd_unregister_id_too_long_raises_error(self):
        """Unregister with agent ID > 256 chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_unregister(
                a2a.argparse.Namespace(project=self.project, id="b" * 300)
            )

    def test_cmd_register_role_too_long_raises_error(self):
        """Register with --role > 512 chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="tester",
                    role="x" * 600, prompt="", cli="", pid=0, upsert=False,
                )
            )

    def test_cmd_register_cli_too_long_raises_error(self):
        """Register with --cli > 128 chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="tester",
                    role="tester", prompt="", cli="c" * 200, pid=0, upsert=False,
                )
            )

    def test_cmd_register_prompt_too_long_raises_error(self):
        """Register with --prompt > 100K chars raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_register(
                a2a.argparse.Namespace(
                    project=self.project, id="tester",
                    role="tester", prompt="p" * 100_001, cli="", pid=0, upsert=False,
                )
            )

    def test_cmd_send_nan_ttl_raises_error(self):
        """Send with --ttl NaN raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_send(
                a2a.argparse.Namespace(
                    project=self.project, to="all", body="hi",
                    **{"from_": "alice", "thread": None, "ttl": float("nan"), "json": False}
                )
            )

    def test_cmd_send_inf_ttl_raises_error(self):
        """Send with --ttl inf raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_send(
                a2a.argparse.Namespace(
                    project=self.project, to="all", body="hi",
                    **{"from_": "alice", "thread": None, "ttl": float("inf"), "json": False}
                )
            )

    def test_recv_future_since_returns_empty(self):
        """recv with --since in the future returns no messages."""
        self._register("alice")
        # Send a message first
        a2a.cmd_send(a2a.argparse.Namespace(
            project=self.project, to="all", body="hello",
            **{"from_": "alice", "thread": None, "ttl": None, "json": False}
        ))
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_="alice", wait=0, all=True,
                peek=False, limit=None, since=9999999999.0, json=True, include_self=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output) if output.strip() else []
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_search_fts_special_chars_does_not_crash(self):
        """Search with special FTS5 characters falls back gracefully to LIKE."""
        import io, sys
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, body, created_at) VALUES (?,?,?)",
            ("alice", "hello (world) [test] *star*", a2a.now())
        )
        conn.commit()
        conn.close()
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_search(a2a.argparse.Namespace(
                project=self.project, query="*star*",
                limit=10, json=False, fts=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("star", output)

    def test_cmd_clear_empty_bus(self):
        """Clear on a bus with no database prints notice and does not crash."""
        import io, sys
        # Use a project that has never been initialized
        phantom_project = f"phantom-{os.getpid()}"
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_clear(
                a2a.argparse.Namespace(project=phantom_project, yes=True)
            )
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("nothing to clear", output.lower())

    def test_cmd_list_json_empty(self):
        """list --json on a bus with no agents returns valid JSON empty array."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_list(
                a2a.argparse.Namespace(project=self.project, json=True)
            )
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_recv_all_shows_all_messages(self):
        """recv --all shows messages to agent even after they've been read."""
        conn = a2a.connect(self.project)
        for agent_id in ("alice", "bob"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (agent_id, "active", a2a.now(), a2a.now())
            )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", "bob", "message for bob", a2a.now())
        )
        conn.execute(
            "INSERT INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
            ("bob", 1, a2a.now())
        )
        conn.commit()
        conn.close()

        # recv without --all should NOT show already-read message
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_="bob", wait=0, all=False,
                peek=False, limit=None, since=None, json=True, include_self=False
            ))
            output_no_all = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        # Should be empty (no unread messages)
        import json
        data_no_all = json.loads(output_no_all) if output_no_all.strip() else []
        self.assertEqual(len(data_no_all), 0, "recv without --all should not return already-read msgs")

        # recv with --all shows all messages regardless of read status
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_="bob", wait=0, all=True,
                peek=False, limit=None, since=None, json=True, include_self=False
            ))
            output_all = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data_all = json.loads(output_all) if output_all.strip() else []
        self.assertGreaterEqual(len(data_all), 1, "recv --all should return already-read msgs")
        self.assertIn("message for bob", [m["body"] for m in data_all])

    def test_recv_all_requires_as(self):
        """recv --all without --as raises SystemExit."""
        with self.assertRaises(SystemExit):
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_=None, wait=0, all=True,
                peek=False, limit=None, since=None, json=False, include_self=False
            ))

    def test_stats_human_readable_output(self):
        """cmd_stats without --json produces expected text format."""
        conn = a2a.connect(self.project)
        conn.execute(
            "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
            ("alice", "active", a2a.now(), a2a.now())
        )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("alice", None, "hello", a2a.now())
        )
        conn.commit()
        conn.close()

        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_stats(a2a.argparse.Namespace(project=self.project, json=False))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        self.assertIn("Project:", output)
        self.assertIn("Messages:", output)
        self.assertIn("broadcast", output)

    def test_stats_top_senders_multiple(self):
        """stats --json reports top senders with correct ordering."""
        conn = a2a.connect(self.project)
        for aid in ("alice", "bob", "charlie"):
            conn.execute(
                "INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)",
                (aid, "active", a2a.now(), a2a.now())
            )
        for i in range(3):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", "bob", f"msg-a-{i}", a2a.now() + i)
            )
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", "alice", "msg-b", a2a.now() + 10)
        )
        conn.commit()
        conn.close()

        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_stats(a2a.argparse.Namespace(project=self.project, json=True))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        data = json.loads(output)
        self.assertEqual(len(data["top_senders"]), 2)
        self.assertEqual(data["top_senders"][0]["agent"], "alice")
        self.assertEqual(data["top_senders"][0]["count"], 3)
        self.assertEqual(data["top_senders"][1]["agent"], "bob")
        self.assertEqual(data["top_senders"][1]["count"], 1)

    def test_search_json_no_matches(self):
        """search --json with no matches returns empty JSON array."""
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_search(a2a.argparse.Namespace(
                project=self.project, query="nonexistent",
                limit=10, json=True, fts=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_peek_empty_bus_human_readable(self):
        """Peek on empty bus with human-readable output does not crash."""
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_peek(a2a.argparse.Namespace(
                project=self.project, limit=10, json=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertEqual(output, "")

    def test_recv_wait_zero_empty_bus(self):
        """recv with --wait=0 on empty bus returns immediately with no messages."""
        self._register("alice")
        import io, sys, json
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            a2a.cmd_recv(a2a.argparse.Namespace(
                project=self.project, as_="alice", wait=0, all=True,
                peek=False, limit=None, since=None, json=True, include_self=False
            ))
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output) if output.strip() else []
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)


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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = make_connection(db_path)
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


class TestProjectNameValidation(unittest.TestCase):
    """Test project name input validation (path traversal prevention)."""

    def test_valid_project_name(self):
        """Valid project names should work normally."""
        name = a2a.project_name("my-project-123")
        self.assertEqual(name, "my-project-123")

    def test_simple_name_from_env(self):
        """Project name from env var should work."""
        os.environ["A2A_PROJECT"] = "simple-test"
        name = a2a.project_name(None)
        self.assertEqual(name, "simple-test")
        del os.environ["A2A_PROJECT"]

    def test_path_separator_rejected(self):
        """Project name containing '/' should be rejected."""
        with self.assertRaises(SystemExit):
            a2a.project_name("../../evil")

    def test_backslash_rejected(self):
        """Project name containing '\\' should be rejected."""
        with self.assertRaises(SystemExit):
            a2a.project_name("evil\\..")

    def test_dot_prefix_rejected(self):
        """Project name starting with '.' should be rejected."""
        with self.assertRaises(SystemExit):
            a2a.project_name(".hidden")

    def test_empty_project_name_rejected(self):
        """Empty project name should be rejected."""
        with self.assertRaises(SystemExit):
            a2a.project_name("")

    def test_whitespace_project_name_rejected(self):
        """Whitespace-only project name should be rejected."""
        with self.assertRaises(SystemExit):
            a2a.project_name("   ")

    def test_env_path_separator_rejected(self):
        """Project name from env var containing '/' should be rejected."""
        os.environ["A2A_PROJECT"] = "a/b"
        with self.assertRaises(SystemExit):
            a2a.project_name(None)
        del os.environ["A2A_PROJECT"]

    def test_unicode_project_name_accepted(self):
        """Valid unicode project names should work normally."""
        name = a2a.project_name("projeto-çñ-测试-проект")
        self.assertEqual(name, "projeto-çñ-测试-проект")

    def test_emoji_project_name_accepted(self):
        """Project names with emoji should be allowed (no path chars)."""
        name = a2a.project_name("project-🚀-test")
        self.assertEqual(name, "project-🚀-test")


class TestTaskCommands(unittest.TestCase):
    """Task CLI commands (phase 2): task-create, task-list, task-status, task-claim, task-complete."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = f"test-{os.getpid()}"
        self.db_path = a2a.db_path(self.project)
        a2a.connect(self.project, create=True).close()

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()
        self.tmpdir.cleanup()

    # ---- task-create ----

    def test_cmd_task_create_basic(self):
        """task-create creates a task with planned status."""
        args = a2a.argparse.Namespace(
            project=self.project, title="Test task", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        )
        a2a.cmd_task_create(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT title, status FROM tasks").fetchone()
        self.assertEqual(row["title"], "Test task")
        self.assertEqual(row["status"], "planned")
        conn.close()

    def test_cmd_task_create_with_assignee_and_description(self):
        """task-create with --description and --assigned-to."""
        args = a2a.argparse.Namespace(
            project=self.project, title="Feature X", description="Implement X",
            assigned_to="alice", priority=1, depends_on=None, json=False,
        )
        a2a.cmd_task_create(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT title, description, assigned_to, priority FROM tasks").fetchone()
        self.assertEqual(row["title"], "Feature X")
        self.assertEqual(row["description"], "Implement X")
        self.assertEqual(row["assigned_to"], "alice")
        self.assertEqual(row["priority"], 1)
        conn.close()

    def test_cmd_task_create_with_dependencies(self):
        """task-create with --depends-on creates dependency records."""
        args1 = a2a.argparse.Namespace(
            project=self.project, title="First", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        )
        a2a.cmd_task_create(args1)
        args2 = a2a.argparse.Namespace(
            project=self.project, title="Second", description=None,
            assigned_to=None, priority=3, depends_on=[1], json=False,
        )
        a2a.cmd_task_create(args2)
        conn = a2a.connect(self.project)
        dep = conn.execute("SELECT * FROM task_deps").fetchone()
        self.assertIsNotNone(dep)
        self.assertEqual(dep["task_id"], 2)
        self.assertEqual(dep["depends_on"], 1)
        conn.close()

    def test_cmd_task_create_empty_title_rejected(self):
        """task-create with empty title exits with error."""
        args = a2a.argparse.Namespace(
            project=self.project, title="  ", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_task_create(args)

    def test_cmd_task_create_json_output(self):
        """task-create --json outputs valid JSON."""
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, title="JSON task", description=None,
                assigned_to=None, priority=3, depends_on=None, json=True,
            )
            a2a.cmd_task_create(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIn("id", data)
        self.assertEqual(data["title"], "JSON task")
        self.assertEqual(data["status"], "planned")

    # ---- task-list ----

    def test_cmd_task_list_empty(self):
        """task-list shows '(no tasks)' when empty."""
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, status=None, assigned_to=None, json=False,
            )
            a2a.cmd_task_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("no tasks", output.lower())

    def test_cmd_task_list_with_tasks(self):
        """task-list shows created tasks."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Task A", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, status=None, assigned_to=None, json=False,
            )
            a2a.cmd_task_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("Task A", output)
        self.assertIn("planned", output)

    def test_cmd_task_list_filter_by_status(self):
        """task-list --status filters correctly."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Task planned", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Task done", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        conn = a2a.connect(self.project)
        conn.execute("UPDATE tasks SET status='done', updated_at=? WHERE id=2", (a2a.now(),))
        conn.commit()
        conn.close()
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, status="done", assigned_to=None, json=False,
            )
            a2a.cmd_task_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("Task done", output)
        self.assertNotIn("Task planned", output)

    def test_cmd_task_list_filter_by_assigned(self):
        """task-list --assigned-to filters by agent."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Alice task", description=None,
            assigned_to="alice", priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Bob task", description=None,
            assigned_to="bob", priority=3, depends_on=None, json=False,
        ))
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, status=None, assigned_to="alice", json=False,
            )
            a2a.cmd_task_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("Alice task", output)
        self.assertNotIn("Bob task", output)

    def test_cmd_task_list_invalid_status_rejected(self):
        """task-list --status invalid exits with error."""
        args = a2a.argparse.Namespace(
            project=self.project, status="invalid", assigned_to=None, json=False,
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_task_list(args)

    def test_cmd_task_list_json_output(self):
        """task-list --json outputs valid JSON array."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Json task", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            args = a2a.argparse.Namespace(
                project=self.project, status=None, assigned_to=None, json=True,
            )
            a2a.cmd_task_list(args)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        data = json.loads(output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Json task")

    # ---- task-status ----

    def test_cmd_task_status_valid_transition(self):
        """task-status follows valid state machine transitions."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="State test", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        args = a2a.argparse.Namespace(
            project=self.project, task_id=1, state="in_progress",
        )
        a2a.cmd_task_status(args)
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "in_progress")
        conn.close()

    def test_cmd_task_status_planned_to_done_rejected(self):
        """planned -> done is invalid."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Skip test", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        args = a2a.argparse.Namespace(
            project=self.project, task_id=1, state="done",
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_task_status(args)

    def test_cmd_task_status_full_workflow(self):
        """Complete workflow: planned -> in_progress -> review_pending -> approved -> done."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Workflow", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        for state in ["in_progress", "review_pending", "approved", "done"]:
            a2a.cmd_task_status(a2a.argparse.Namespace(
                project=self.project, task_id=1, state=state,
            ))
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status, completed_at FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "done")
        self.assertIsNotNone(row["completed_at"])
        conn.close()

    def test_cmd_task_status_blocked_and_unblock(self):
        """blocked -> in_progress is valid."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Block test", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="in_progress",
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="blocked",
        ))
        conn = a2a.connect(self.project)
        self.assertEqual(conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()["status"], "blocked")
        conn.close()
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="in_progress",
        ))
        conn = a2a.connect(self.project)
        self.assertEqual(conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()["status"], "in_progress")
        conn.close()

    def test_cmd_task_status_done_is_terminal(self):
        """done -> any state is rejected."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Terminal", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="in_progress",
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="done",
        ))
        for state in ["planned", "in_progress", "review_pending", "approved", "blocked"]:
            with self.assertRaises(SystemExit):
                a2a.cmd_task_status(a2a.argparse.Namespace(
                    project=self.project, task_id=1, state=state,
                ))

    def test_cmd_task_status_unknown_task(self):
        """task-status on non-existent task exits with error."""
        args = a2a.argparse.Namespace(
            project=self.project, task_id=9999, state="in_progress",
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_task_status(args)

    def test_cmd_task_status_invalid_state_rejected(self):
        """task-status with invalid status exits with error."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Bad status", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        args = a2a.argparse.Namespace(
            project=self.project, task_id=1, state="invalid_status",
        )
        with self.assertRaises(SystemExit):
            a2a.cmd_task_status(args)

    # ---- task-claim ----

    def test_cmd_task_claim(self):
        """task-claim assigns agent and sets in_progress."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Claimable", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_claim(a2a.argparse.Namespace(
            project=self.project, task_id=1, as_="alice",
        ))
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status, assigned_to, claimed_at FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["assigned_to"], "alice")
        self.assertIsNotNone(row["claimed_at"])
        conn.close()

    def test_cmd_task_claim_already_done_rejected(self):
        """task-claim on a done task exits with error."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Done task", description=None,
            assigned_to=None, priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="in_progress",
        ))
        a2a.cmd_task_status(a2a.argparse.Namespace(
            project=self.project, task_id=1, state="done",
        ))
        with self.assertRaises(SystemExit):
            a2a.cmd_task_claim(a2a.argparse.Namespace(
                project=self.project, task_id=1, as_="alice",
            ))

    def test_cmd_task_claim_assigned_to_other_rejected(self):
        """task-claim on task assigned to another agent exits with error."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Others task", description=None,
            assigned_to="bob", priority=3, depends_on=None, json=False,
        ))
        with self.assertRaises(SystemExit):
            a2a.cmd_task_claim(a2a.argparse.Namespace(
                project=self.project, task_id=1, as_="alice",
            ))

    def test_cmd_task_claim_unknown_task(self):
        """task-claim on non-existent task exits with error."""
        with self.assertRaises(SystemExit):
            a2a.cmd_task_claim(a2a.argparse.Namespace(
                project=self.project, task_id=9999, as_="alice",
            ))

    def test_cmd_task_claim_reclaim_owned(self):
        """task-claim on already-owned task is OK."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Mine", description=None,
            assigned_to="alice", priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_claim(a2a.argparse.Namespace(
            project=self.project, task_id=1, as_="alice",
        ))
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "in_progress")
        conn.close()

    # ---- task-complete ----

    def test_cmd_task_complete_with_result(self):
        """task-complete sets done and records result."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Completable", description=None,
            assigned_to="alice", priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_claim(a2a.argparse.Namespace(
            project=self.project, task_id=1, as_="alice",
        ))
        a2a.cmd_task_complete(a2a.argparse.Namespace(
            project=self.project, task_id=1, result="All done!", as_="alice",
        ))
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status, result, completed_at FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["result"], "All done!")
        self.assertIsNotNone(row["completed_at"])
        conn.close()

    def test_cmd_task_complete_without_result(self):
        """task-complete without --result still works."""
        a2a.cmd_task_create(a2a.argparse.Namespace(
            project=self.project, title="Quick task", description=None,
            assigned_to="bob", priority=3, depends_on=None, json=False,
        ))
        a2a.cmd_task_claim(a2a.argparse.Namespace(
            project=self.project, task_id=1, as_="bob",
        ))
        a2a.cmd_task_complete(a2a.argparse.Namespace(
            project=self.project, task_id=1, result=None, as_="bob",
        ))
        conn = a2a.connect(self.project)
        row = conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()
        self.assertEqual(row["status"], "done")
        conn.close()

    def test_cmd_task_complete_unknown_task(self):
        """task-complete on non-existent task exits with error."""
        with self.assertRaises(SystemExit):
            a2a.cmd_task_complete(a2a.argparse.Namespace(
                project=self.project, task_id=9999, result="nope", as_="alice",
            ))


if __name__ == "__main__":
    unittest.main()
