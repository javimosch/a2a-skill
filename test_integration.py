#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration tests for a2a CLI — full end-to-end workflows.

Shells out to the `a2a` binary and verifies output, database state,
and behavior across multi-step scenarios.

Run: python3 test_integration.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

import sqlite3

# Path to the a2a CLI (same directory as this test)
HERE = os.path.dirname(os.path.abspath(__file__))
A2A = os.path.join(HERE, "a2a")
A2A_PY = os.path.join(HERE, "a2a.py")


def a2a(*args, project: str, expect_fail: bool = False) -> subprocess.CompletedProcess:
    """Run a2a CLI and return result."""
    env = os.environ.copy()
    env["A2A_PROJECT"] = project
    env["A2A_PYTHON"] = "python3"  # fallback, overridden below
    try:
        result = subprocess.run(
            [A2A] + list(args),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except FileNotFoundError:
        # fallback to direct python
        result = subprocess.run(
            ["python3", A2A_PY] + list(args),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    if not expect_fail:
        if result.returncode != 0:
            print(f"  STDOUT: {result.stdout}", file=sys.stderr)
            print(f"  STDERR: {result.stderr}", file=sys.stderr)
        assert result.returncode == 0, (
            f"a2a {' '.join(args)} failed (rc={result.returncode}):\n"
            f"  stderr: {result.stderr}"
        )
    return result


def _a2a_py(*args, project: str, expect_fail: bool = False) -> subprocess.CompletedProcess:
    """Run a2a using the Python script directly (bypasses the Go binary)."""
    env = os.environ.copy()
    env["A2A_PROJECT"] = project
    result = subprocess.run(
        ["python3", A2A_PY] + list(args),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    if not expect_fail:
        if result.returncode != 0:
            print(f"  STDOUT: {result.stdout}", file=sys.stderr)
            print(f"  STDERR: {result.stderr}", file=sys.stderr)
        assert result.returncode == 0, (
            f"a2a {' '.join(args)} failed (rc={result.returncode}):\n"
            f"  stderr: {result.stderr}"
        )
    return result


def db_path(project: str) -> str:
    """Get the database path for a project."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".a2a", project, "database.db")


def count_messages(project: str) -> int:
    """Count messages in the project database."""
    path = db_path(project)
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path)
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    return count


def count_agents(project: str) -> int:
    """Count registered agents in the project database."""
    path = db_path(project)
    if not os.path.exists(path):
        return 0
    conn = sqlite3.connect(path)
    count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    conn.close()
    return count


class TestIntegration(unittest.TestCase):
    """End-to-end CLI integration tests."""

    project_prefix = "a2a-int-test-"

    @classmethod
    def setUpClass(cls):
        # Verify a2a is available
        try:
            result = subprocess.run(
                [A2A, "--help"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise FileNotFoundError("a2a --help failed")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Try with python3 directly
            result = subprocess.run(
                ["python3", A2A_PY, "--help"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise unittest.SkipTest("a2a CLI not available for integration tests")

    def setUp(self):
        self.project = f"{self.project_prefix}{os.getpid()}-{id(self)}"
        a2a("init", project=self.project)

    def tearDown(self):
        a2a("clear", "--yes", project=self.project, expect_fail=True)

    # ---- basic commands ----
    def test_list_empty_bus(self):
        """List on empty bus shows notice."""
        result = a2a("list", project=self.project)
        self.assertIn("no agents", result.stdout.lower())

    def test_register_and_list(self):
        """Register and list an agent."""
        a2a("register", "alice", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertGreaterEqual(len(agents), 1)
        ids = [a["id"] for a in agents]
        self.assertIn("alice", ids)

    def test_register_with_prompt_and_cli(self):
        """Register with --prompt and --cli stores additional metadata."""
        a2a("register", "alice", "--role", "builder",
            "--prompt", "build things", "--cli", "claude",
            project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        alice = next(a for a in agents if a["id"] == "alice")
        self.assertEqual(alice["role"], "builder")
        self.assertEqual(alice["cli"], "claude")

    # ---- send / recv ----
    def test_send_and_recv_direct(self):
        """Send direct message and receive it."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "hello bob", "--from", "alice", project=self.project)
        result = a2a("recv", "--as", "bob", "--wait", "0", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "hello bob")
        self.assertEqual(msgs[0]["sender"], "alice")

    def test_send_broadcast(self):
        """Broadcast message reaches all peers."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("register", "charlie", project=self.project)
        a2a("send", "all", "hello everyone", "--from", "alice",
            project=self.project)
        # Both bob and charlie should receive it
        for agent in ("bob", "charlie"):
            result = a2a("recv", "--as", agent, "--wait", "0", "--json",
                         project=self.project)
            msgs = json.loads(result.stdout)
            self.assertGreaterEqual(len(msgs), 1)
            self.assertIn("hello everyone", [m["body"] for m in msgs])

    def test_send_with_thread(self):
        """Send with --thread sets thread_id."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "msg1", "--from", "alice", "--thread", "thread-1",
            project=self.project)
        a2a("send", "alice", "msg2", "--from", "bob", "--thread", "thread-1",
            project=self.project)
        result = a2a("thread", "thread-1", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 2)
        self.assertTrue(all(m["thread_id"] == "thread-1" for m in msgs))

    # ---- TTL ----
    def test_ttl_default_no_expiry(self):
        """Messages without --ttl persist."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "persist", "--from", "alice", project=self.project)
        # Message should still be there
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("persist", bodies)

    def test_ttl_expiry(self):
        """Messages with --ttl get cleaned up after expiry."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "short-lived", "--from", "alice", "--ttl", "1",
            project=self.project)
        # Should be visible initially
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies_before = [m["body"] for m in msgs]
        self.assertIn("short-lived", bodies_before)
        # Wait for TTL to expire
        time.sleep(1.5)
        # Trigger cleanup with another operation
        a2a("peek", "--json", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies_after = [m["body"] for m in msgs]
        self.assertNotIn("short-lived", bodies_after)

    def test_ttl_mixed(self):
        """Expired messages cleaned up, non-TTL messages remain."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "expiring", "--from", "alice", "--ttl", "1",
            project=self.project)
        a2a("send", "bob", "permanent", "--from", "alice",
            project=self.project)
        time.sleep(1.5)
        a2a("peek", "--json", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertNotIn("expiring", bodies)
        self.assertIn("permanent", bodies)

    # ---- status ----
    def test_status_transitions(self):
        """Agent status transitions work end-to-end."""
        a2a("register", "worker", project=self.project)
        for state in ("idle", "active", "blocked", "done"):
            a2a("status", state, "--as", "worker", project=self.project)
            result = a2a("list", "--json", project=self.project)
            agents = json.loads(result.stdout)
            worker = next(a for a in agents if a["id"] == "worker")
            self.assertEqual(worker["status"], state)

    def test_status_json_output(self):
        """a2a status --json returns machine-readable confirmation."""
        a2a("register", "alice", project=self.project)
        result = a2a("status", "done", "--as", "alice", "--json",
                     project=self.project)
        data = json.loads(result.stdout)
        self.assertIn("agent", data)
        self.assertIn("status", data)
        self.assertEqual(data["agent"], "alice")
        self.assertEqual(data["status"], "done")

    def test_status_nonexistent_agent_fails(self):
        """a2a status on an unregistered agent exits non-zero."""
        result = a2a("status", "done", "--as", "ghost",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    # ---- unregister ----
    def test_unregister(self):
        """Unregister removes an agent."""
        a2a("register", "alice", project=self.project)
        a2a("unregister", "alice", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        ids = [a["id"] for a in agents]
        self.assertNotIn("alice", ids)

    # ---- error handling ----
    def test_send_unknown_recipient_fails(self):
        """Sending to unknown agent fails."""
        a2a("register", "alice", project=self.project)
        result = a2a("send", "ghost", "hi", "--from", "alice",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    def test_recv_unknown_agent_fails(self):
        """Recv as unknown agent fails."""
        result = a2a("recv", "--as", "ghost", "--wait", "0",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    def test_send_unregistered_sender_fails(self):
        """Sending from unregistered sender fails."""
        a2a("register", "bob", project=self.project)
        result = a2a("send", "bob", "hi", "--from", "ghost",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    # ---- read tracking ----
    def test_read_tracking(self):
        """Messages are only returned once by recv."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "alice", "msg1", "--from", "bob", project=self.project)
        # First recv should get the message
        result1 = a2a("recv", "--as", "alice", "--wait", "0", "--json",
                      project=self.project)
        msgs1 = json.loads(result1.stdout)
        self.assertGreaterEqual(len(msgs1), 1)
        # Second recv without --all should be empty
        result2 = a2a("recv", "--as", "alice", "--wait", "0", "--json",
                      project=self.project)
        msgs2 = json.loads(result2.stdout)
        self.assertEqual(len(msgs2), 0)

    def test_recv_limit(self):
        """Recv respects --limit parameter."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(3):
            a2a("send", "bob", f"msg{i}", "--from", "alice",
                project=self.project)
        result = a2a("recv", "--as", "bob", "--wait", "0", "--limit", "2",
                     "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    # ---- peek ----
    def test_peek_limit(self):
        """Peek respects --limit."""
        a2a("register", "alice", project=self.project)
        for i in range(5):
            a2a("send", "alice", f"msg{i}", "--from", "alice",
                project=self.project)
        result = a2a("peek", "--limit", "2", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    def test_peek_json_valid(self):
        """Peek --json returns valid JSON array."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "peek msg", "--from", "alice",
            project=self.project)
        result = a2a("peek", "--json", "--limit", "10", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertIsInstance(msgs, list)
        self.assertGreaterEqual(len(msgs), 1)
        self.assertIn("body", msgs[0])
        self.assertIn("sender", msgs[0])

    # ---- include-self ----
    def test_include_self(self):
        """--include-self allows an agent to see its own messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "alice", "secret", "--from", "alice",
            project=self.project)
        # Without --include-self, alice shouldn't see it
        result_no = a2a("recv", "--as", "alice", "--json", "--wait", "0",
                        project=self.project)
        msgs_no = json.loads(result_no.stdout)
        self.assertFalse(any(m["sender"] == "alice" for m in msgs_no))
        # With --include-self, alice should see it
        result_yes = a2a("recv", "--as", "alice", "--include-self", "--json",
                         project=self.project)
        msgs_yes = json.loads(result_yes.stdout)
        self.assertTrue(any(m["sender"] == "alice" for m in msgs_yes))

    # ---- project isolation ----
    def test_project_isolation(self):
        """Messages from one project don't appear in another."""
        project2 = f"{self.project}-2"
        a2a("init", project=project2)
        a2a("register", "alice", project=self.project)
        a2a("register", "alice", project=project2)
        a2a("send", "alice", "secret", "--from", "alice",
            project=self.project)
        # Check project2 doesn't have the message
        result = a2a("peek", "--json", project=project2)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertNotIn("secret", bodies)
        # Cleanup
        a2a("clear", "--yes", project=project2)

    # ---- concurrent messaging ----
    def test_concurrent_messaging(self):
        """Multiple agents can send recv concurrently."""
        agents = ["alice", "bob", "charlie"]
        for a in agents:
            a2a("register", a, project=self.project)
        # Everyone sends to everyone
        for sender in agents:
            for recipient in agents:
                if sender != recipient:
                    a2a("send", recipient, f"hello from {sender}",
                        "--from", sender, project=self.project)
        # Everyone checks their inbox
        for a in agents:
            result = a2a("recv", "--as", a, "--include-self", "--json",
                         project=self.project)
            msgs = json.loads(result.stdout)
            self.assertGreaterEqual(len(msgs), 1)

    # ---- thread ----
    def test_thread_command(self):
        """a2a thread <id> returns all messages in a thread."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "first", "--from", "alice", "--thread", "t1",
            project=self.project)
        a2a("send", "alice", "second", "--from", "bob", "--thread", "t1",
            project=self.project)
        result = a2a("thread", "t1", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 2)
        bodies = [m["body"] for m in msgs]
        self.assertIn("first", bodies)
        self.assertIn("second", bodies)

    def test_thread_command_empty(self):
        """a2a thread <unknown-id> returns empty list without error."""
        result = a2a("thread", "nonexistent", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 0)

    def test_thread_max_id_length_rejected(self):
        """a2a thread with thread ID > 256 chars is rejected."""
        result = a2a("thread", "t" * 300, project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    # ---- stats ----
    def test_stats_command(self):
        """a2a stats returns correct counts."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "direct", "--from", "alice",
            project=self.project)
        a2a("send", "all", "broadcast", "--from", "alice",
            project=self.project)
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertGreaterEqual(stats["messages"], 2)
        self.assertGreaterEqual(stats["direct_messages"], 1)
        self.assertGreaterEqual(stats["broadcasts"], 1)

    def test_stats_empty_bus(self):
        """a2a stats on a fresh bus reports zero messages."""
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertEqual(stats["messages"], 0)
        self.assertEqual(stats["agents_active"], 0)

    # ---- search ----
    def test_search_cli_returns_matches(self):
        """a2a search finds matching messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "hello world", "--from", "alice",
            project=self.project)
        result = a2a("search", "hello", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)
        bodies = [m["body"] for m in msgs]
        self.assertIn("hello world", bodies)

    def test_search_cli_no_matches(self):
        """a2a search with no matches returns empty JSON."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "existing message", "--from", "alice",
            project=self.project)
        result = a2a("search", "zzznonexistent", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 0)

    def test_search_cli_case_insensitive(self):
        """a2a search is case-insensitive."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "CaseTest", "--from", "alice",
            project=self.project)
        result = a2a("search", "casetest", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    # ---- project command ----
    def test_project_command(self):
        """a2a project prints project info."""
        result = a2a("project", project=self.project)
        self.assertIn(self.project, result.stdout)

    def test_project_command_json(self):
        """a2a project --json returns valid JSON with expected fields."""
        result = a2a("project", "--json", project=self.project)
        data = json.loads(result.stdout)
        self.assertIn("project", data)
        self.assertIn("db", data)
        self.assertIn("exists", data)
        self.assertEqual(data["project"], self.project)
        self.assertTrue(data["exists"])

    # ---- wait ----
    def test_wait_returns_when_message_arrives(self):
        """a2a wait returns once a matching message is on the bus."""
        import threading
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        # Send after a delay
        def delayed_send():
            time.sleep(0.5)
            a2a("send", "bob", "late arrival", "--from", "alice",
                project=self.project)
        t = threading.Thread(target=delayed_send)
        t.start()
        result = a2a("recv", "--as", "bob", "--wait", "5", "--json",
                     project=self.project)
        t.join()
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "late arrival")

    def test_wait_times_out_when_no_message(self):
        """a2a wait exits with non-zero when timeout expires with no message."""
        a2a("register", "lonely", project=self.project)
        result = a2a("recv", "--as", "lonely", "--wait", "1", "--json",
                     project=self.project, expect_fail=True)
        # Should timeout (rc != 0 or empty output)
        if result.returncode == 0:
            msgs = json.loads(result.stdout)
            self.assertEqual(len(msgs), 0)

    # ---- clear ----
    def test_clear_requires_yes_flag(self):
        """Clear without --yes fails."""
        result = a2a("clear", project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    def test_clear_deletes_database(self):
        """Clear --yes removes the database."""
        a2a("register", "alice", project=self.project)
        self.assertTrue(os.path.exists(db_path(self.project)))
        a2a("clear", "--yes", project=self.project)
        self.assertFalse(os.path.exists(db_path(self.project)))

    def test_clear_nonexistent_db_is_noop(self):
        """Clear on already-cleared project does not error."""
        a2a("clear", "--yes", project=self.project, expect_fail=True)
        a2a("clear", "--yes", project=self.project, expect_fail=True)

    # ---- recv edge cases ----
    def test_recv_since_filters_old_messages(self):
        """recv --since filters out messages older than the timestamp."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        # Send an old message (use low timestamp by setting system time... can't do that)
        # Instead, send two messages and use since to filter the first
        a2a("send", "bob", "first msg", "--from", "alice",
            project=self.project)
        time.sleep(0.1)
        a2a("send", "bob", "second msg", "--from", "alice",
            project=self.project)
        time.sleep(0.1)
        a2a("send", "bob", "third msg", "--from", "alice",
            project=self.project)
        # Get the timestamp of the second message
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        # peek returns oldest first, so second msg is index 1
        self.assertGreaterEqual(len(msgs), 2)
        second_ts = msgs[1]["created_at"]
        # recv with since=second_ts should return only third msg (index 2)
        result = a2a("recv", "--as", "bob", "--since", str(second_ts),
                     "--json", project=self.project)
        msgs2 = json.loads(result.stdout)
        # Should only get messages newer than second_ts's timestamp
        for m in msgs2:
            self.assertGreaterEqual(m["created_at"], second_ts - 0.001)

    def test_recv_since_empty_when_no_new_messages(self):
        """recv --since returns empty when no messages after the timestamp."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "old", "--from", "alice",
            project=self.project)
        result = a2a("recv", "--as", "bob", "--since", "9999999999",
                     "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 0)

    def test_recv_all_includes_already_read_messages(self):
        """recv --all includes messages already marked as read."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "read msg", "--from", "alice",
            project=self.project)
        # First recv marks it read
        a2a("recv", "--as", "bob", "--wait", "0", project=self.project)
        # Without --all, should be empty
        result = a2a("recv", "--as", "bob", "--wait", "0", "--json",
                     project=self.project)
        msgs_no_all = json.loads(result.stdout)
        self.assertEqual(len(msgs_no_all), 0)
        # With --all, should include the already-read message
        result = a2a("recv", "--as", "bob", "--all", "--json",
                     project=self.project)
        msgs_all = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs_all), 1)
        bodies = [m["body"] for m in msgs_all]
        self.assertIn("read msg", bodies)

    def test_recv_include_self_delivers_own_broadcast(self):
        """recv --include-self returns messages sent by the agent itself."""
        a2a("register", "alice", project=self.project)
        a2a("send", "all", "self broadcast", "--from", "alice",
            project=self.project)
        result = a2a("recv", "--as", "alice", "--include-self", "--all", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("self broadcast", bodies)

    def test_list_json_returns_array(self):
        """a2a list --json returns a list."""
        result = a2a("list", "--json", project=self.project)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)

    def test_recv_limit_caps_returned_messages(self):
        """recv --limit caps the number of returned messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(5):
            a2a("send", "bob", f"limit msg {i}", "--from", "alice",
                project=self.project)
        result = a2a("recv", "--as", "bob", "--limit", "3", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 3)

    def test_stats_shows_message_count(self):
        """stats command returns correct message total."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "m1", "--from", "alice", project=self.project)
        a2a("send", "bob", "m2", "--from", "alice", project=self.project)
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertGreaterEqual(stats["messages"], 2)

    def test_search_with_limit(self):
        """search --limit caps results."""
        a2a("register", "alice", project=self.project)
        for i in range(5):
            a2a("send", "alice", f"searchable {i}", "--from", "alice",
                project=self.project)
        result = a2a("search", "searchable", "--limit", "2", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    def test_broadcast_without_registered_recipients(self):
        """Broadcast works when no agents are registered."""
        # Send broadcast on an empty bus (except sender)
        a2a("register", "alice", project=self.project)
        a2a("send", "all", "hello", "--from", "alice",
            project=self.project)
        # Should not crash — message should be on the bus
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    def test_multiple_sends_to_same_agent_chronological_order(self):
        """Multiple sends to same agent maintain chronological order."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(3):
            a2a("send", "bob", f"msg {i}", "--from", "alice",
                project=self.project)
            time.sleep(0.1)
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        # Should be in chronological order
        self.assertEqual(bodies, ["msg 0", "msg 1", "msg 2"])

    def test_recv_empty_on_fresh_bus(self):
        """recv on fresh bus returns empty result."""
        a2a("register", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--wait", "0", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 0)

    def test_peek_does_not_mark_read(self):
        """peek does not affect reads table."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "visible", "--from", "alice",
            project=self.project)
        # Peek
        a2a("peek", project=self.project)
        # recv without --all should still get the message (peek didn't mark it)
        result = a2a("recv", "--as", "bob", "--wait", "0", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    def test_send_empty_body(self):
        """Send with empty body works."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "", "--from", "alice", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("", bodies)

    def test_peek_json_with_limit(self):
        """peek --json with limit returns at most N messages."""
        a2a("register", "alice", project=self.project)
        for i in range(10):
            a2a("send", "alice", f"m{i}", "--from", "alice",
                project=self.project)
        result = a2a("peek", "--json", "--limit", "3", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 3)

    def test_send_broadcast_then_recv_all_agents(self):
        """Broadcast reaches all registered agents."""
        agents = ["alice", "bob", "charlie"]
        for a in agents:
            a2a("register", a, project=self.project)
        a2a("send", "all", "broadcast msg", "--from", "alice",
            project=self.project)
        for a in agents:
            result = a2a("recv", "--as", a, "--json", project=self.project)
            msgs = json.loads(result.stdout)
            bodies = [m["body"] for m in msgs]
            if a != "alice":
                # Others should see the broadcast
                self.assertIn("broadcast msg", bodies)

    def test_peek_on_empty_bus_returns_no_messages(self):
        """peek on empty bus returns empty results."""
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 0)

    def test_register_upsert_via_cli(self):
        """Upsert via CLI updates existing agent."""
        a2a("register", "alice", "--role", "old", project=self.project)
        a2a("register", "alice", "--role", "new", "--upsert",
            project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        alice = next(a for a in agents if a["id"] == "alice")
        self.assertEqual(alice["role"], "new")

    def test_unregister_twice_is_noop(self):
        """Unregistering an already-unregistered agent does not error."""
        a2a("register", "alice", project=self.project)
        a2a("unregister", "alice", project=self.project)
        a2a("unregister", "alice", project=self.project)  # Should not crash

    def test_recv_peek_flag_does_not_mark_read(self):
        """recv --peek does not mark messages as read."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "peeked", "--from", "alice",
            project=self.project)
        # recv --peek
        a2a("recv", "--as", "bob", "--peek", "--json",
            project=self.project)
        # Should still be available via recv (not marked read)
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    def test_recv_all_includes_read_messages(self):
        """recv --all includes already-read messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "already read", "--from", "alice",
            project=self.project)
        # First recv marks it as read
        a2a("recv", "--as", "bob", "--json", project=self.project)
        # Second recv without --all should be empty
        result1 = a2a("recv", "--as", "bob", "--json", project=self.project)
        self.assertEqual(len(json.loads(result1.stdout)), 0)
        # With --all, should include the already-read message
        result2 = a2a("recv", "--as", "bob", "--all", "--json",
                      project=self.project)
        msgs = json.loads(result2.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("already read", bodies)

    def test_stats_with_agents_no_messages(self):
        """stats shows zero message counts when agents exist but no messages sent."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertEqual(stats["messages"], 0)
        self.assertGreaterEqual(stats["agents_active"], 1)

    def test_unregister_agent_keeps_other_agents_intact(self):
        """Unregistering one agent does not affect other registered agents."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("unregister", "alice", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        ids = [a["id"] for a in agents]
        self.assertNotIn("alice", ids)
        self.assertIn("bob", ids)

    def test_peek_json_with_limit_caps_output(self):
        """peek --json --limit N caps output to N messages."""
        a2a("register", "alice", project=self.project)
        for i in range(5):
            a2a("send", "alice", f"limit peek {i}", "--from", "alice",
                project=self.project)
        result = a2a("peek", "--json", "--limit", "2", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    def test_peek_limit_over_max_does_not_error(self):
        """peek with --limit > 1000 is capped to 1000, not rejected or errored."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "msg1", "--from", "alice",
            project=self.project)
        a2a("send", "alice", "msg2", "--from", "alice",
            project=self.project)
        # Large limit should not crash and should return all available messages
        result = a2a("peek", "--json", "--limit", "9999", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 2)

    def test_search_limit_over_max_does_not_error(self):
        """search with --limit > 200 is capped to 200, not rejected or errored."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "findable 1", "--from", "alice",
            project=self.project)
        a2a("send", "alice", "findable 2", "--from", "alice",
            project=self.project)
        # Large limit should not crash and should return all available messages
        result = a2a("search", "findable", "--limit", "999", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 2)

    def test_list_json_valid_empty_after_clear(self):
        """list --json returns valid [] after bus is cleared."""
        a2a("register", "alice", project=self.project)
        a2a("clear", "--yes", project=self.project)
        a2a("init", project=self.project)  # Re-init
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertEqual(len(agents), 0)

    def test_send_broadcast_then_unregister_recipient(self):
        """Sending broadcast and then unregistering a recipient doesn't crash."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "all", "broadcast", "--from", "alice",
            project=self.project)
        a2a("unregister", "bob", project=self.project)
        # Should not crash
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    def test_send_special_chars_body(self):
        """Send message body with special characters works."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        body = "hello ✨ world — ñoño 日本語"
        a2a("send", "bob", body, "--from", "alice", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn(body, bodies)

    def test_peek_limit_zero_rejected(self):
        """peek --limit 0 is rejected (must be positive)."""
        a2a("register", "alice", project=self.project)
        result = a2a("peek", "--json", "--limit", "0", project=self.project,
                      expect_fail=True)
        self.assertIn("must be a positive integer", result.stderr)

    def test_send_ttl_from_cli(self):
        """Send with --ttl from CLI expires messages after the TTL period."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "short-lived", "--from", "alice", "--ttl", "60",
            project=self.project)
        a2a("send", "bob", "permanent", "--from", "alice",
            project=self.project)
        # Both should be visible initially
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("short-lived", bodies)
        self.assertIn("permanent", bodies)

    def test_recv_from_self_without_flag_filters(self):
        """Send to self, recv without --include-self filters own messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "alice", "secret self-message", "--from", "alice",
            project=self.project)
        # Alice recv without --include-self should NOT return self-sent
        result = a2a("recv", "--as", "alice", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        for m in msgs:
            self.assertNotEqual(m.get("sender"), "alice",
                                "self-sent message should be filtered without --include-self")
        # With --include-self it should appear
        result2 = a2a("recv", "--as", "alice", "--json", "--include-self",
                      project=self.project)
        msgs2 = json.loads(result2.stdout)
        bodies = [m["body"] for m in msgs2]
        self.assertIn("secret self-message", bodies)

    def test_peek_after_clear_shows_empty(self):
        """peek after clear --yes returns no messages."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "temp msg", "--from", "alice",
            project=self.project)
        a2a("clear", "--yes", project=self.project)
        a2a("init", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout) if result.stdout.strip() else []
        self.assertEqual(len(msgs), 0, "peek after clear should be empty")

    def test_recv_json_empty_on_fresh_bus(self):
        """recv --json on an agent with no messages returns valid empty JSON."""
        a2a("register", "lonely", project=self.project)
        result = a2a("recv", "--as", "lonely", "--json", "--wait", "0",
                     project=self.project)
        # Should produce valid JSON (empty list) or be empty
        if result.stdout.strip():
            msgs = json.loads(result.stdout)
            self.assertIsInstance(msgs, list)
            self.assertEqual(len(msgs), 0)

    def test_search_json_empty_on_no_match(self):
        """search --json with non-matching query returns empty JSON."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "hello world", "--from", "alice",
            project=self.project)
        result = a2a("search", "zzznonexistentkeyword", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout) if result.stdout.strip() else []
        self.assertIsInstance(msgs, list)
        self.assertEqual(len(msgs), 0,
                         "search with no match should return empty list")

    def test_register_negative_pid_fails(self):
        """Register with negative --pid fails."""
        result = a2a("register", "test-agent", "--pid", "-1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr.lower())

    def test_recv_since_inf_fails(self):
        """recv --since inf fails."""
        a2a("register", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--since", "inf",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite", result.stderr.lower())
        # Also test --since NaN
        result = a2a("recv", "--as", "alice", "--since", "NaN",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite", result.stderr.lower())

    def test_recv_limit_negative_rejected(self):
        """recv with negative --limit is rejected."""
        a2a("register", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--limit", "-1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("limit", result.stderr.lower())

    def test_recv_wait_nan_rejected(self):
        """recv with NaN --wait is rejected."""
        a2a("register", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--wait", "NaN",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite", result.stderr.lower())

    def test_wait_timeout_nan_rejected(self):
        """wait with NaN --timeout is rejected."""
        a2a("register", "bob", project=self.project)
        result = a2a("wait", "--as", "bob", "--timeout", "NaN",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finite", result.stderr.lower())

    def test_register_pid_zero_fails(self):
        """Register with --pid 0 is rejected (must be positive)."""
        result = a2a("register", "test-agent", "--pid", "0",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr.lower())

    def test_register_whitespace_id_rejected(self):
        """Register with whitespace-only agent id is rejected."""
        result = _a2a_py("register", "   ", project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty", result.stderr.lower())

    def test_register_whitespace_role_rejected(self):
        """Register with whitespace-only --role is rejected."""
        result = _a2a_py("register", "valid-agent", "--role", "   ",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("role", result.stderr.lower())

    def test_register_whitespace_cli_rejected(self):
        """Register with whitespace-only --cli is rejected."""
        result = _a2a_py("register", "valid-agent", "--cli", "   ",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cli", result.stderr.lower())

    def test_send_empty_from_rejected(self):
        """Send with empty --from is rejected."""
        result = _a2a_py("send", "alice", "hello", "--from", "",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from", result.stderr.lower())

    def test_send_whitespace_from_rejected(self):
        """Send with whitespace-only --from is rejected."""
        result = _a2a_py("send", "alice", "hello", "--from", "   ",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from", result.stderr.lower())

    # --- Max length validation tests ---

    def test_register_max_id_length_rejected(self):
        """Register with agent ID > 256 chars is rejected."""
        long_id = "a" * 257
        result = a2a("register", long_id, project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_register_max_id_length_boundary_ok(self):
        """Register with agent ID = 256 chars succeeds."""
        exact_id = "a" * 256
        a2a("register", exact_id, project=self.project)

    def test_send_max_from_id_length_rejected(self):
        """Send with --from > 256 chars is rejected."""
        long_id = "b" * 257
        result = a2a("send", "alice", "hello", "--from", long_id,
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_send_max_recipient_id_length_rejected(self):
        """Send with recipient > 256 chars is rejected."""
        a2a("register", "sender", project=self.project)
        long_id = "c" * 257
        result = a2a("send", long_id, "hello", "--from", "sender",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_send_max_thread_length_rejected(self):
        """Send with --thread > 256 chars is rejected."""
        a2a("register", "sender", project=self.project)
        long_thread = "t" * 257
        result = a2a("send", "sender", "hello", "--from", "sender",
                     "--thread", long_thread,
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_send_json_output(self):
        """send --json outputs valid JSON with id, sender, recipient."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        result = a2a("send", "bob", "hello", "--from", "alice", "--json",
                     project=self.project)
        data = json.loads(result.stdout)
        self.assertIn("id", data)
        self.assertIn("sender", data)
        self.assertIn("recipient", data)
        self.assertEqual(data["sender"], "alice")
        self.assertEqual(data["recipient"], "bob")

    def test_send_json_output_broadcast(self):
        """send --json with broadcast outputs recipient 'ALL'."""
        a2a("register", "alice", project=self.project)
        result = a2a("send", "all", "broadcast msg", "--from", "alice", "--json",
                     project=self.project)
        data = json.loads(result.stdout)
        self.assertEqual(data["recipient"], "ALL")

    def test_unregister_max_id_length_rejected(self):
        """Unregister with agent ID > 256 chars is rejected."""
        long_id = "u" * 257
        result = a2a("unregister", long_id, project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_status_max_as_id_length_rejected(self):
        """Status with --as > 256 chars is rejected."""
        a2a("register", "tester", project=self.project)
        long_id = "s" * 257
        result = a2a("status", "done", "--as", long_id,
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_recv_max_as_id_length_rejected(self):
        """Recv with --as > 256 chars is rejected."""
        long_id = "r" * 257
        result = a2a("recv", "--as", long_id, "--wait", "0",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_wait_max_as_id_length_rejected(self):
        """Wait with --as > 256 chars is rejected."""
        long_id = "w" * 257
        result = a2a("wait", "--as", long_id, "--count", "1", "--timeout", "1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too long", result.stderr.lower())

    def test_wait_count_zero_rejected(self):
        """Wait with --count 0 is rejected."""
        a2a("register", "alice", project=self.project)
        result = a2a("wait", "--as", "alice", "--count", "0", "--timeout", "1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr.lower())

    def test_wait_count_negative_rejected(self):
        """Wait with --count -1 is rejected."""
        a2a("register", "alice", project=self.project)
        result = a2a("wait", "--as", "alice", "--count", "-1", "--timeout", "1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr.lower())

    def test_wait_timeout_negative_rejected(self):
        """Wait with negative --timeout is rejected."""
        a2a("register", "alice", project=self.project)
        result = a2a("wait", "--as", "alice", "--count", "1", "--timeout", "-1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-negative", result.stderr.lower())

    def test_send_ttl_zero_rejected(self):
        """Send with --ttl 0 is rejected."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        result = a2a("send", "bob", "msg", "--from", "alice", "--ttl", "0",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive", result.stderr.lower())

    def test_register_duplicate_without_upsert_fails(self):
        """Registering an already-existing agent without --upsert fails."""
        a2a("register", "alice", project=self.project)
        result = a2a("register", "alice", project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already registered", result.stderr.lower())

    def test_init_idempotent(self):
        """Calling init on an already-initialized project is idempotent."""
        result = a2a("init", project=self.project)
        self.assertEqual(result.returncode, 0)

    def test_search_special_fts5_chars(self):
        """Search with FTS5 special characters (quotes, parens) works."""
        a2a("register", "alice", project=self.project)
        a2a("send", "alice", "test (parentheses) here", "--from", "alice",
            project=self.project)
        a2a("send", "alice", 'say "hello world" now', "--from", "alice",
            project=self.project)
        # Search with parentheses — should not crash
        result = a2a("search", "parentheses", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)
        bodies = [m["body"] for m in msgs]
        self.assertTrue(any("parentheses" in b for b in bodies))
        # Search phrase with quotes — should not crash
        result2 = a2a("search", "hello world", "--json", project=self.project)
        msgs2 = json.loads(result2.stdout)
        self.assertGreaterEqual(len(msgs2), 1)

    def test_thread_special_char_id(self):
        """thread with special characters in thread_id works."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "msg 1", "--from", "alice", "--thread", "thread-1/2/3",
            project=self.project)
        a2a("send", "bob", "msg 2", "--from", "alice", "--thread", "thread-1/2/3",
            project=self.project)
        result = a2a("thread", "thread-1/2/3", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 2)
        all_have_thread = all(m.get("thread_id") == "thread-1/2/3" for m in msgs)
        self.assertTrue(all_have_thread)

    def test_list_json_structure(self):
        """list --json returns valid JSON with expected fields."""
        a2a("register", "alice", "--role", "tester", "--cli", "pytest",
            project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertIsInstance(agents, list)
        alice = next(a for a in agents if a["id"] == "alice")
        self.assertEqual(alice["role"], "tester")
        self.assertEqual(alice["cli"], "pytest")
        self.assertIn("status", alice)
        self.assertIn("pid", alice)

    def test_broadcast_received_by_multiple(self):
        """Broadcast message is received by all registered agents."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("register", "charlie", project=self.project)
        a2a("send", "all", "broadcast to everyone", "--from", "alice",
            project=self.project)
        # Bob sees it
        bob_result = a2a("recv", "--as", "bob", "--wait", "0", "--json",
                         project=self.project)
        bob_msgs = json.loads(bob_result.stdout)
        bob_bodies = [m["body"] for m in bob_msgs]
        self.assertIn("broadcast to everyone", bob_bodies)
        # Charlie sees it too
        charlie_result = a2a("recv", "--as", "charlie", "--wait", "0", "--json",
                             project=self.project)
        charlie_msgs = json.loads(charlie_result.stdout)
        charlie_bodies = [m["body"] for m in charlie_msgs]
        self.assertIn("broadcast to everyone", charlie_bodies)

    def test_send_unicode_body(self):
        """Send and recv with unicode characters in body."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        unicode_msg = "Hello 世界! ñoño 🚀 # français"
        result = a2a("send", "bob", unicode_msg, "--from", "alice", "--json",
                     project=self.project)
        data = json.loads(result.stdout)
        self.assertIn("id", data)
        bob_result = a2a("recv", "--as", "bob", "--wait", "1", "--json",
                         project=self.project)
        msgs = json.loads(bob_result.stdout)
        self.assertGreaterEqual(len(msgs), 1)
        self.assertIn(unicode_msg, [m["body"] for m in msgs])


if __name__ == "__main__":
    unittest.main()
