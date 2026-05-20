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

    # ---- Registration & Lifecycle ----

    def test_list_empty_bus(self):
        """a2a list on a fresh bus prints empty notice (no crash)."""
        result = a2a("list", project=self.project)
        self.assertIn("no agents", result.stdout.lower())

    def test_register_and_list(self):
        """Register agents and list them."""
        a2a("register", "agent-a", "--role", "dev", project=self.project)
        a2a("register", "agent-b", "--role", "critic", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertEqual(len(agents), 2)
        ids = {a["id"] for a in agents}
        self.assertIn("agent-a", ids)
        self.assertIn("agent-b", ids)

    def test_register_with_prompt_and_cli(self):
        """Register with optional fields."""
        a2a("register", "worker", "--role", "builder",
            "--prompt", "Build things", "--cli", "pi", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertEqual(len(agents), 1)
        a = agents[0]
        self.assertEqual(a["id"], "worker")
        self.assertEqual(a["role"], "builder")
        self.assertEqual(a["cli"], "pi")

    # ---- Sending & Receiving ----

    def test_send_and_recv_direct(self):
        """Send a direct message and receive it."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Hello Bob!", "--from", "alice", project=self.project)
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["sender"], "alice")
        self.assertEqual(msgs[0]["recipient"], "bob")
        self.assertEqual(msgs[0]["body"], "Hello Bob!")

    def test_send_broadcast(self):
        """Broadcast reaches all agents."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("register", "carol", project=self.project)
        a2a("send", "all", "Team standup!", "--from", "alice", project=self.project)

        # Both bob and carol should receive it
        for agent in ("bob", "carol"):
            result = a2a("recv", "--as", agent, "--json", project=self.project)
            msgs = json.loads(result.stdout)
            self.assertGreaterEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["body"], "Team standup!")
            self.assertIsNone(msgs[0]["recipient"])  # broadcast

    def test_send_with_thread(self):
        """Send with --thread sets thread_id."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Threaded msg", "--from", "alice",
            "--thread", "topic-42", project=self.project)
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs[0]["thread_id"], "topic-42")

    # ---- TTL ----

    def test_ttl_default_no_expiry(self):
        """Messages without --ttl persist."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Persist me", "--from", "alice", project=self.project)
        # Should still be there
        self.assertEqual(count_messages(self.project), 1)

    def test_ttl_expiry(self):
        """Messages with --ttl get cleaned up after expiry."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        # Send with 1s TTL, then wait for it to expire
        a2a("send", "bob", "Expiring msg", "--from", "alice",
            "--ttl", "1", project=self.project)
        self.assertEqual(count_messages(self.project), 1)
        time.sleep(1.5)
        # Peek triggers cleanup
        a2a("peek", project=self.project)
        self.assertEqual(count_messages(self.project), 0)

    def test_ttl_mixed(self):
        """Expired messages cleaned up, non-TTL messages remain."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Keep me", "--from", "alice", project=self.project)
        a2a("send", "bob", "Delete me", "--from", "alice",
            "--ttl", "1", project=self.project)
        time.sleep(1.5)
        a2a("peek", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        bodies = [m["body"] for m in msgs]
        self.assertIn("Keep me", bodies)
        self.assertNotIn("Delete me", bodies)

    # ---- Status ----

    def test_status_transitions(self):
        """Agent status transitions work end-to-end."""
        a2a("register", "worker", project=self.project)
        for state in ("idle", "active", "blocked", "done"):
            a2a("status", state, "--as", "worker", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertEqual(agents[0]["status"], "done")

    def test_status_json_output(self):
        """a2a status --json returns machine-readable confirmation."""
        a2a("register", "worker", project=self.project)
        result = a2a("status", "active", "--as", "worker", "--json",
                     project=self.project)
        info = json.loads(result.stdout)
        self.assertEqual(info["agent"], "worker")
        self.assertEqual(info["status"], "active")
        self.assertIn("last_seen", info)

    def test_status_nonexistent_agent_fails(self):
        """a2a status on an unregistered agent exits non-zero."""
        result = a2a("status", "active", "--as", "ghost",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    # ---- Unregister ----

    def test_unregister(self):
        """Unregister removes an agent."""
        a2a("register", "ghost", project=self.project)
        self.assertEqual(count_agents(self.project), 1)
        a2a("unregister", "ghost", project=self.project)
        self.assertEqual(count_agents(self.project), 0)

    # ---- Error Handling ----

    def test_send_unknown_recipient_fails(self):
        """Sending to unknown agent should fail."""
        a2a("register", "alice", project=self.project)
        result = a2a(
            "send", "phantom", "hi", "--from", "alice",
            project=self.project, expect_fail=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown recipient", result.stderr.lower())

    def test_recv_unknown_agent_fails(self):
        """Receiving as unknown agent should fail."""
        result = a2a(
            "recv", "--as", "nobody", project=self.project, expect_fail=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown agent", result.stderr.lower())

    def test_send_unregistered_sender_fails(self):
        """Sending from unregistered agent should fail."""
        result = a2a(
            "send", "bob", "hi", "--from", "unauthorized",
            project=self.project, expect_fail=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown sender", result.stderr.lower())

    # ---- Read Tracking ----

    def test_read_tracking(self):
        """Messages are marked read after recv, not shown again."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Read me", "--from", "alice", project=self.project)
        # First recv — should see the message
        result1 = a2a("recv", "--as", "bob", "--json", project=self.project)
        self.assertEqual(len(json.loads(result1.stdout)), 1)
        # Second recv without --all — should be empty (already read)
        result2 = a2a("recv", "--as", "bob", "--json", project=self.project)
        self.assertEqual(len(json.loads(result2.stdout)), 0)
        # With --all — should show again
        result3 = a2a("recv", "--as", "bob", "--all", "--json", project=self.project)
        self.assertGreaterEqual(len(json.loads(result3.stdout)), 1)

    # ---- Limit flag ----

    def test_recv_limit(self):
        """a2a recv --limit N returns at most N messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(5):
            a2a("send", "bob", f"msg {i}", "--from", "alice",
                project=self.project)
        result = a2a("recv", "--as", "bob", "--limit", "2", "--all",
                     "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    def test_peek_limit(self):
        """a2a peek --limit N returns at most N messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(5):
            a2a("send", "all", f"broadcast {i}", "--from", "alice",
                project=self.project)
        result = a2a("peek", "--limit", "3", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 3)

    # ---- JSON Output ----

    def test_peek_json_valid(self):
        """Peek --json produces valid JSON structures."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "data", "--from", "alice", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertIsInstance(msgs, list)
        self.assertGreaterEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertIn("id", msg)
        self.assertIn("sender", msg)
        self.assertIn("recipient", msg)
        self.assertIn("body", msg)
        self.assertIn("created_at", msg)

    # ---- include-self ----

    def test_include_self(self):
        """--include-self allows an agent to see its own messages."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "alice", "Self note", "--from", "alice", project=self.project)
        # Without --include-self, alice shouldn't see it
        result_no = a2a("recv", "--as", "alice", "--json", project=self.project)
        self.assertEqual(len(json.loads(result_no.stdout)), 0)
        # With --include-self, alice should see it
        result_yes = a2a("recv", "--as", "alice", "--include-self", "--json", project=self.project)
        self.assertGreaterEqual(len(json.loads(result_yes.stdout)), 1)

    # ---- Project isolation ----

    def test_project_isolation(self):
        """Messages in one project don't bleed to another."""
        proj_a = self.project + "-a"
        proj_b = self.project + "-b"
        try:
            a2a("init", project=proj_a)
            a2a("init", project=proj_b)
            a2a("register", "agent", project=proj_a)
            a2a("register", "agent", project=proj_b)
            a2a("send", "agent", "secret", "--from", "agent", project=proj_a)
            self.assertEqual(count_messages(proj_a), 1)
            self.assertEqual(count_messages(proj_b), 0)
        finally:
            a2a("clear", "--yes", project=proj_a, expect_fail=True)
            a2a("clear", "--yes", project=proj_b, expect_fail=True)

    # ---- Concurrent agents ----

    def test_concurrent_messaging(self):
        """Multiple agents can send and receive independently."""
        agents = [f"agent-{i}" for i in range(5)]
        for a in agents:
            a2a("register", a, project=self.project)
        # All agents broadcast
        for a in agents:
            a2a("send", "all", f"Hello from {a}", "--from", a,
                project=self.project)
        # Each agent should have received 5 messages (from all including self)
        for a in agents:
            result = a2a("recv", "--as", a, "--include-self", "--json",
                         project=self.project)
            msgs = json.loads(result.stdout)
            bodies = {m["body"] for m in msgs}
            for other in agents:
                self.assertIn(f"Hello from {other}", bodies)


    # ---- Thread command ----

    def test_thread_command(self):
        """a2a thread <id> returns all messages in a thread."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        tid = "qa-thread-001"
        a2a("send", "bob", "first in thread", "--from", "alice",
            "--thread", tid, project=self.project)
        a2a("send", "bob", "second in thread", "--from", "alice",
            "--thread", tid, project=self.project)
        a2a("send", "bob", "unrelated message", "--from", "alice",
            project=self.project)
        result = a2a("thread", tid, "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 2)
        bodies = {m["body"] for m in msgs}
        self.assertIn("first in thread", bodies)
        self.assertIn("second in thread", bodies)
        self.assertNotIn("unrelated message", bodies)

    def test_thread_command_empty(self):
        """a2a thread <unknown-id> returns empty list without error."""
        result = a2a("thread", "nonexistent-thread-id", "--json",
                     project=self.project)
        self.assertEqual(result.returncode, 0)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs, [])

    # ---- Stats command ----

    def test_stats_command(self):
        """a2a stats returns correct counts."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "all", "broadcast one", "--from", "alice",
            project=self.project)
        a2a("send", "bob", "direct one", "--from", "alice",
            project=self.project)
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertEqual(stats["messages"], 2)
        self.assertEqual(stats["broadcasts"], 1)
        self.assertEqual(stats["direct_messages"], 1)
        self.assertGreaterEqual(stats["agents_active"], 2)

    def test_stats_empty_bus(self):
        """a2a stats on a fresh bus reports zero messages."""
        result = a2a("stats", "--json", project=self.project)
        stats = json.loads(result.stdout)
        self.assertEqual(stats["messages"], 0)

    # ---- Search command ----

    def test_search_cli_returns_matches(self):
        """a2a search finds messages containing the query term."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "the authentication service is down",
            "--from", "alice", project=self.project)
        a2a("send", "bob", "deployment completed successfully",
            "--from", "alice", project=self.project)
        result = a2a("search", "authentication", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 1)
        self.assertIn("authentication", msgs[0]["body"])

    def test_search_cli_no_matches(self):
        """a2a search returns empty list when nothing matches."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "hello world", "--from", "alice",
            project=self.project)
        result = a2a("search", "zzznomatch", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs, [])

    def test_search_cli_case_insensitive(self):
        """a2a search is case-insensitive."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "Deploy Complete", "--from", "alice",
            project=self.project)
        result = a2a("search", "deploy", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertGreaterEqual(len(msgs), 1)

    # ---- Project command ----

    def test_project_command(self):
        """a2a project reports the active project name."""
        result = a2a("project", project=self.project)
        self.assertIn(self.project, result.stdout)

    def test_project_command_json(self):
        """a2a project always outputs JSON with project name and db path."""
        result = a2a("project", project=self.project)
        info = json.loads(result.stdout)
        self.assertEqual(info["project"], self.project)
        self.assertIn("db", info)
        self.assertIn("exists", info)

    # ---- Wait command ----

    def test_wait_returns_when_message_arrives(self):
        """a2a wait returns once a matching message is on the bus."""
        import threading
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)

        def send_after_delay():
            time.sleep(0.5)
            a2a("send", "bob", "wake up bob", "--from", "alice",
                project=self.project)

        t = threading.Thread(target=send_after_delay)
        t.start()
        result = a2a("wait", "--as", "bob", "--timeout", "5",
                     project=self.project)
        t.join(timeout=6)
        self.assertEqual(result.returncode, 0)

    def test_wait_times_out_when_no_message(self):
        """a2a wait exits with non-zero when timeout expires with no message."""
        a2a("register", "bob", project=self.project)
        result = a2a("wait", "--as", "bob", "--timeout", "1",
                     project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    # ---- Clear command ----

    def test_clear_requires_yes_flag(self):
        """a2a clear without --yes exits non-zero."""
        result = a2a("clear", project=self.project, expect_fail=True)
        self.assertNotEqual(result.returncode, 0)

    def test_clear_deletes_database(self):
        """a2a clear --yes removes the project database."""
        a2a("register", "alice", project=self.project)
        self.assertTrue(os.path.exists(db_path(self.project)))
        a2a("clear", "--yes", project=self.project)
        self.assertFalse(os.path.exists(db_path(self.project)))

    def test_clear_nonexistent_db_is_noop(self):
        """a2a clear --yes on a project with no DB reports nothing to clear."""
        import uuid
        fresh_project = f"a2a-clear-test-{uuid.uuid4().hex[:8]}"
        result = a2a("clear", "--yes", project=fresh_project)
        self.assertIn("nothing", result.stdout.lower())

    # ---- recv --since flag ----

    def test_recv_since_filters_old_messages(self):
        """recv --since <ts> returns only messages created after ts."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "old message", "--from", "alice",
            project=self.project)
        # record timestamp after first message
        import time
        ts = time.time()
        time.sleep(0.05)
        a2a("send", "bob", "new message", "--from", "alice",
            project=self.project)
        result = a2a("recv", "--as", "bob", "--since", str(ts), "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "new message")

    def test_recv_since_empty_when_no_new_messages(self):
        """recv --since <future_ts> returns [] when nothing is newer."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "old message", "--from", "alice",
            project=self.project)
        import time
        future_ts = time.time() + 3600
        result = a2a("recv", "--as", "bob", "--since", str(future_ts),
                     "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs, [])

    def test_recv_all_includes_already_read_messages(self):
        """recv --all returns messages even if already read."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "first read", "--from", "alice", project=self.project)
        # First recv marks message as read
        a2a("recv", "--as", "bob", "--json", project=self.project)
        # Second recv without --all returns empty
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs, [])
        # recv --all should still return it
        result = a2a("recv", "--as", "bob", "--all", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 1)

    def test_recv_include_self_delivers_own_broadcast(self):
        """recv --include-self returns messages sent by the agent itself."""
        a2a("register", "alice", project=self.project)
        a2a("send", "all", "my own broadcast", "--from", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--include-self", "--all", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertTrue(any(m["body"] == "my own broadcast" for m in msgs))

    def test_list_json_returns_array(self):
        """list --json output is a valid JSON array with agent fields."""
        a2a("register", "alice", "--role", "planner", project=self.project)
        result = a2a("list", "--json", project=self.project)
        agents = json.loads(result.stdout)
        self.assertIsInstance(agents, list)
        self.assertEqual(len(agents), 1)
        self.assertIn("id", agents[0])
        self.assertIn("role", agents[0])
        self.assertEqual(agents[0]["id"], "alice")

    def test_peek_json_valid(self):
        """peek --json returns valid JSON array."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "peeked message", "--from", "alice", project=self.project)
        result = a2a("peek", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertIsInstance(msgs, list)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "peeked message")

    def test_recv_limit_caps_returned_messages(self):
        """recv --limit 2 returns at most 2 messages even if 4 are waiting."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        for i in range(4):
            a2a("send", "bob", f"msg {i}", "--from", "alice", project=self.project)
        result = a2a("recv", "--as", "bob", "--limit", "2", "--json",
                     project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 2)

    def test_stats_shows_message_count(self):
        """stats command returns correct message total."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "msg1", "--from", "alice", project=self.project)
        a2a("send", "all", "broadcast", "--from", "alice", project=self.project)
        result = a2a("stats", "--json", project=self.project)
        data = json.loads(result.stdout)
        self.assertEqual(data["messages"], 2)
        self.assertEqual(data["broadcasts"], 1)
        self.assertEqual(data["direct_messages"], 1)

    def test_search_with_limit(self):
        """search --limit 1 returns at most 1 result."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "hello world", "--from", "alice", project=self.project)
        a2a("send", "bob", "hello universe", "--from", "alice", project=self.project)
        result = a2a("search", "hello", "--json", "--limit", "1", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertLessEqual(len(msgs), 1)

    def test_broadcast_without_registered_recipients(self):
        """Broadcast to 'all' works even if no other agents are registered."""
        a2a("register", "alice", project=self.project)
        # Only alice is registered — broadcast should still succeed
        a2a("send", "all", "lonely broadcast", "--from", "alice",
            project=self.project)
        self.assertEqual(count_messages(self.project), 1)

    def test_multiple_sends_to_same_agent_chronological_order(self):
        """recv returns messages in chronological order when sent to same agent."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "first msg", "--from", "alice", project=self.project)
        a2a("send", "bob", "second msg", "--from", "alice", project=self.project)
        a2a("send", "bob", "third msg", "--from", "alice", project=self.project)
        result = a2a("recv", "--as", "bob", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["body"], "first msg")
        self.assertEqual(msgs[1]["body"], "second msg")
        self.assertEqual(msgs[2]["body"], "third msg")

    def test_recv_empty_on_fresh_bus(self):
        """recv on a bus with no messages returns empty without error."""
        a2a("register", "alice", project=self.project)
        result = a2a("recv", "--as", "alice", "--json", project=self.project)
        msgs = json.loads(result.stdout)
        self.assertEqual(msgs, [])

    def test_peek_does_not_mark_read(self):
        """peek does not mark messages as read — recv still sees them."""
        a2a("register", "alice", project=self.project)
        a2a("register", "bob", project=self.project)
        a2a("send", "bob", "peekable msg", "--from", "alice", project=self.project)
        # Peek should see the message
        result_peek = a2a("peek", "--json", project=self.project)
        peek_msgs = json.loads(result_peek.stdout)
        self.assertEqual(len(peek_msgs), 1)
        # Recv after peek should still see it as unread
        result_recv = a2a("recv", "--as", "bob", "--json", project=self.project)
        recv_msgs = json.loads(result_recv.stdout)
        self.assertEqual(len(recv_msgs), 1)


if __name__ == "__main__":
    unittest.main()
