#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for async a2a modules: A2AClientAsync, PriorityClientAsync, RoutingClientAsync.

All tests skip gracefully when aiosqlite is not installed.
Install: pip install aiosqlite
"""

import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from test_helpers import make_connection
from pathlib import Path

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

SKIP_MSG = "aiosqlite not installed (pip install aiosqlite)"


def run_async(coro):
    """Run a coroutine synchronously for test use."""
    return asyncio.get_event_loop().run_until_complete(coro)


DB_SCHEMA = """
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
"""


def _setup_db(project_dir: Path):
    """Initialize a test database with schema and two agents."""
    db_path = project_dir / "database.db"
    conn = make_connection(db_path)
    conn.executescript(DB_SCHEMA)
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
    return db_path


@unittest.skipUnless(HAS_AIOSQLITE, SKIP_MSG)
class TestA2AClientAsync(unittest.TestCase):
    """Tests for A2AClientAsync."""

    @classmethod
    def setUpClass(cls):
        cls.test_home = tempfile.mkdtemp()
        cls.original_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.test_home

    @classmethod
    def tearDownClass(cls):
        if cls.original_home:
            os.environ["HOME"] = cls.original_home

    def setUp(self):
        from a2a_client_async import A2AClientAsync
        self.project = f"async-test-{id(self)}"
        project_dir = Path(self.test_home) / ".a2a" / self.project
        project_dir.mkdir(parents=True, exist_ok=True)
        _setup_db(project_dir)
        self.alice = A2AClientAsync(self.project, "alice")
        self.bob = A2AClientAsync(self.project, "bob")

    def tearDown(self):
        run_async(self.alice.close())
        run_async(self.bob.close())

    def test_constructor_empty_agent_id_raises_error(self):
        """A2AClientAsync with empty agent_id raises ValueError."""
        from a2a_client_async import A2AClientAsync
        with self.assertRaises(ValueError):
            A2AClientAsync(self.project, "")
        with self.assertRaises(ValueError):
            A2AClientAsync(self.project, "   ")

    def test_constructor_empty_project_raises_error(self):
        """A2AClientAsync with empty project raises ValueError."""
        from a2a_client_async import A2AClientAsync
        with self.assertRaises(ValueError):
            A2AClientAsync("", "alice")
        with self.assertRaises(ValueError):
            A2AClientAsync("   ", "alice")

    def test_send_direct_returns_id(self):
        """send() returns a positive message ID."""
        msg_id = run_async(self.alice.send("bob", "Hello Bob"))
        self.assertIsInstance(msg_id, int)
        self.assertGreater(msg_id, 0)

    def test_send_broadcast(self):
        """send() to 'all' stores a broadcast."""
        msg_id = run_async(self.alice.send("all", "Broadcast"))
        self.assertGreater(msg_id, 0)

    def test_recv_direct(self):
        """recv() retrieves a direct message."""
        run_async(self.alice.send("bob", "Hello from Alice"))
        messages = run_async(self.bob.recv(wait=1))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["sender"], "alice")
        self.assertEqual(messages[0]["body"], "Hello from Alice")

    def test_recv_broadcast(self):
        """recv() retrieves broadcast messages."""
        run_async(self.alice.send("all", "Broadcast message"))
        messages = run_async(self.bob.recv(wait=1))
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0]["recipient"])

    def test_recv_marks_as_read(self):
        """Second recv() returns empty (messages already read)."""
        run_async(self.alice.send("bob", "Once"))
        run_async(self.bob.recv(wait=1))
        second = run_async(self.bob.recv(wait=0))
        self.assertEqual(len(second), 0)

    def test_recv_excludes_self_by_default(self):
        """recv() without include_self=True does not return own messages."""
        run_async(self.alice.send("alice", "To self"))
        messages = run_async(self.alice.recv(wait=0, include_self=False))
        self.assertEqual(len(messages), 0)

    def test_recv_include_self(self):
        """recv(include_self=True) returns self messages."""
        run_async(self.alice.send("alice", "Self message"))
        messages = run_async(self.alice.recv(wait=1, include_self=True))
        self.assertGreater(len(messages), 0)
        bodies = [m["body"] for m in messages]
        self.assertIn("Self message", bodies)

    def test_peek_does_not_mark_read(self):
        """peek() does not mark messages read."""
        run_async(self.alice.send("bob", "Peek target"))
        run_async(self.bob.peek(limit=10))
        messages = run_async(self.bob.recv(wait=1))
        self.assertGreater(len(messages), 0)

    def test_list_peers(self):
        """list_peers() returns registered agents."""
        peers = run_async(self.alice.list_peers())
        ids = {p["id"] for p in peers}
        self.assertIn("alice", ids)
        self.assertIn("bob", ids)

    def test_set_get_status(self):
        """set_status/get_status roundtrip."""
        run_async(self.alice.set_status("idle"))
        status = run_async(self.alice.get_status())
        self.assertEqual(status, "idle")

    def test_set_status_invalid_raises_error(self):
        """set_status() with invalid status raises ValueError (async)."""
        from a2a_client_async import A2AClientAsync
        # Register a separate agent using sync client for status tests
        conn = make_connection(self.alice.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO agents(id, role, status, created_at, last_seen) "
            "VALUES (?,?,?,?,?)",
            ("status-test-agent", "tester", "active", time.time(), time.time())
        )
        conn.commit()
        conn.close()
        client = A2AClientAsync(self.project, "status-test-agent")
        try:
            with self.assertRaises(ValueError):
                run_async(client.set_status("invalid"))
            with self.assertRaises(ValueError):
                run_async(client.set_status(""))
            # Valid statuses should still work
            run_async(client.set_status("idle"))
            status = run_async(client.get_status())
            self.assertEqual(status, "idle")
            run_async(client.set_status("done"))
        finally:
            run_async(client.close())

    def test_get_status_other_agent(self):
        """get_status() for another agent."""
        status = run_async(self.alice.get_status("bob"))
        self.assertEqual(status, "active")

    def test_stats(self):
        """stats() returns message and agent counts."""
        run_async(self.alice.send("bob", "Msg1"))
        run_async(self.alice.send("all", "Broadcast"))
        stats = run_async(self.alice.stats())
        self.assertGreaterEqual(stats["messages"], 2)
        self.assertGreaterEqual(stats["broadcasts"], 1)
        self.assertIn("agents_active", stats)
        # top_senders keys should match sync client format
        if stats["top_senders"]:
            self.assertIn("agent", stats["top_senders"][0])
            self.assertIn("count", stats["top_senders"][0])

    def test_search(self):
        """search() finds messages by keyword."""
        run_async(self.alice.send("bob", "unique-keyword-xyz"))
        results = run_async(self.alice.search("unique-keyword-xyz"))
        self.assertGreater(len(results), 0)
        self.assertIn("unique-keyword-xyz", results[0]["body"])

    def test_search_case_insensitive(self):
        """search() is case-insensitive."""
        run_async(self.alice.send("bob", "Test MESSAGE With Case"))
        results = run_async(self.alice.search("message"))
        self.assertGreater(len(results), 0)
        self.assertIn("Test MESSAGE With Case", results[0]["body"])

    def test_recv_cleans_up_expired_messages(self):
        """recv() triggers TTL cleanup so expired messages are not returned."""
        run_async(self.alice.send("bob", "will expire", ttl_seconds=1))
        time.sleep(1.2)
        messages = run_async(self.bob.recv(wait=1))
        bodies = [m["body"] for m in messages]
        self.assertNotIn("will expire", bodies)

    def test_peek_cleans_up_expired_messages(self):
        """peek() triggers TTL cleanup so expired messages don't appear."""
        run_async(self.alice.send("bob", "ttl will vanish", ttl_seconds=1))
        time.sleep(1.2)
        messages = run_async(self.bob.peek(limit=10))
        bodies = [m["body"] for m in messages]
        self.assertNotIn("ttl will vanish", bodies)

    def test_context_manager(self):
        """Async context manager closes connection on exit."""
        from a2a_client_async import A2AClientAsync

        async def _use():
            async with A2AClientAsync(self.project, "alice") as client:
                msg_id = await client.send("bob", "Context msg")
                return msg_id

        msg_id = run_async(_use())
        self.assertGreater(msg_id, 0)

    def test_wal_mode_enabled(self):
        """Database connection uses WAL journal mode."""
        async def _check():
            conn = await self.alice._connect()
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            return row[0]

        mode = run_async(_check())
        self.assertEqual(mode, "wal")

    def test_mkdir_guard(self):
        """_connect() creates parent directory if missing."""
        from a2a_client_async import A2AClientAsync
        project = f"mkdir-test-{int(time.time())}"
        # Don't pre-create the directory
        client = A2AClientAsync(project, "agent")

        async def _connect_and_close():
            await client._connect()
            await client.close()

        run_async(_connect_and_close())
        db_path = Path(self.test_home) / ".a2a" / project / "database.db"
        self.assertTrue(db_path.parent.exists())

    def test_recv_empty_wait_returns_immediately(self):
        """recv(wait=0) returns immediately without blocking."""
        import time
        start = time.time()
        messages = run_async(self.bob.recv(wait=0))
        elapsed = time.time() - start
        self.assertEqual(len(messages), 0)
        self.assertLess(elapsed, 2, "recv with wait=0 should not block")

    def test_peek_limit_non_positive_rejected(self):
        """peek(limit <= 0) raises ValueError."""
        run_async(self.alice.send("bob", "test message"))
        for bad_limit in (0, -1):
            with self.assertRaises(ValueError):
                run_async(self.alice.peek(limit=bad_limit))

    def test_recv_negative_wait_raises_value_error(self):
        """recv(wait=-1) raises ValueError (must match sync client)."""
        with self.assertRaises(ValueError) as ctx:
            run_async(self.bob.recv(wait=-1))
        self.assertIn("non-negative", str(ctx.exception))

    def test_recv_nan_wait_raises_value_error(self):
        """recv(wait=nan) raises ValueError (must match sync client)."""
        with self.assertRaises(ValueError) as ctx:
            run_async(self.bob.recv(wait=float("nan")))
        self.assertIn("finite", str(ctx.exception))

    def test_recv_inf_wait_raises_value_error(self):
        """recv(wait=inf) raises ValueError (must match sync client)."""
        with self.assertRaises(ValueError) as ctx:
            run_async(self.bob.recv(wait=float("inf")))
        self.assertIn("finite", str(ctx.exception))

    def test_send_to_empty_string_raises_value_error(self):
        """send() with empty recipient raises ValueError (async)."""
        from a2a_client_async import A2AClientAsync
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                with self.assertRaises(ValueError):
                    await client.send("", "empty")
                with self.assertRaises(ValueError):
                    await client.send("   ", "whitespace")
        run_async(_test())

    def test_send_ttl_non_positive_rejected(self):
        """send() with ttl <= 0 raises ValueError (async)."""
        from a2a_client_async import A2AClientAsync
        run_async(self.alice.register("tester"))
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                for bad_ttl in (0, -1, -5):
                    with self.assertRaises(ValueError):
                        await client.send("bob", "bad ttl", ttl_seconds=bad_ttl)

    def test_send_empty_body(self):
        """send() with empty body creates a message with empty content (async)."""
        from a2a_client_async import A2AClientAsync
        run_async(self.alice.register("tester"))
        run_async(self.bob.register("tester"))
        async def _do():
            async with A2AClientAsync(self.project, "alice") as client:
                msg_id = await client.send("bob", "")
                return msg_id
        msg_id = run_async(_do())
        self.assertGreater(msg_id, 0)
        msgs = run_async(self.bob.recv(wait=1))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "")

    def test_send_with_thread_and_ttl_combined(self):
        """send() with both thread_id and ttl_seconds works together (async)."""
        run_async(self.alice.register("tester"))
        run_async(self.bob.register("tester"))
        from a2a_client_async import A2AClientAsync
        async def _do():
            async with A2AClientAsync(self.project, "alice") as client:
                msg_id = await client.send("bob", "threaded ttl msg",
                                            thread_id="async-thread-1", ttl_seconds=3600)
                return msg_id
        msg_id = run_async(_do())
        self.assertGreater(msg_id, 0)
        msgs = run_async(self.bob.recv(wait=1))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["thread_id"], "async-thread-1")

    def test_send_body_too_long_rejected(self):
        """send() with body > 100K chars raises ValueError (async)."""
        from a2a_client_async import A2AClientAsync
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                with self.assertRaises(ValueError):
                    await client.send("bob", "x" * 100_001)
        run_async(_test())

    def test_send_empty_thread_id_rejected(self):
        """send() with empty thread_id raises ValueError (async)."""
        from a2a_client_async import A2AClientAsync
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                with self.assertRaises(ValueError):
                    await client.send("bob", "msg", thread_id="")
                with self.assertRaises(ValueError):
                    await client.send("bob", "msg", thread_id="   ")
        run_async(_test())

    def test_search_returns_empty(self):
        """search() returns empty list when no messages match (async)."""
        run_async(self.alice.register("tester"))
        from a2a_client_async import A2AClientAsync
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                results = await client.search("nonexistent-term-xyz")
                return results
        results = run_async(_test())
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_send_body_at_boundary_accepted(self):
        """send() with body=100000 chars (exact boundary) is accepted (async)."""
        from a2a_client_async import A2AClientAsync
        run_async(self.alice.register("tester"))
        async def _test():
            async with A2AClientAsync(self.project, "alice") as client:
                return await client.send("bob", "x" * 100_000)
        msg_id = run_async(_test())
        self.assertGreater(msg_id, 0)

    def test_close_idempotent(self):
        """close() called twice does not raise (async)."""
        from a2a_client_async import A2AClientAsync
        client = A2AClientAsync(self.project, "close-test")
        async def _do():
            await client._connect()
            await client.close()
            # Second close should be a no-op
            await client.close()
        run_async(_do())

    def test_recv_unread_only_excludes_read_messages(self):
        """recv(unread_only=True) excludes messages already marked as read (async)."""
        from a2a_client_async import A2AClientAsync
        run_async(self.alice.register("tester"))
        run_async(self.bob.register("tester"))

        async def _test():
            async with A2AClientAsync(self.project, "alice") as alice:
                await alice.send("bob", "msg1")
            async with A2AClientAsync(self.project, "bob") as bob:
                # First recv reads the message
                msgs1 = await bob.recv(wait=0, unread_only=True)
                self.assertEqual(len(msgs1), 1)
                # Second recv with unread_only should return empty
                msgs2 = await bob.recv(wait=0, unread_only=True)
                return len(msgs2)
        count = run_async(_test())
        self.assertEqual(count, 0)

    def test_peek_very_large_limit(self):
        """peek(limit=99999) does not crash (async)."""
        from a2a_client_async import A2AClientAsync
        run_async(self.alice.register("tester"))
        async def _test():
            async with A2AClientAsync(self.project, "alice") as alice:
                messages = await alice.peek(limit=99999)
                return messages
        messages = run_async(_test())
        self.assertIsInstance(messages, list)


@unittest.skipUnless(HAS_AIOSQLITE, SKIP_MSG)
class TestPriorityClientAsync(unittest.TestCase):
    """Tests for PriorityClientAsync."""

    @classmethod
    def setUpClass(cls):
        cls.test_home = tempfile.mkdtemp()
        cls.original_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.test_home

    @classmethod
    def tearDownClass(cls):
        if cls.original_home:
            os.environ["HOME"] = cls.original_home

    def setUp(self):
        from a2a_priority_async import PriorityClientAsync
        self.project = f"prio-async-{id(self)}"
        project_dir = Path(self.test_home) / ".a2a" / self.project
        project_dir.mkdir(parents=True, exist_ok=True)
        _setup_db(project_dir)
        self.client = PriorityClientAsync(self.project, "alice")

    def test_instantiation_succeeds(self):
        """PriorityClientAsync can be instantiated when aiosqlite is present."""
        self.assertIsNotNone(self.client)

    def test_wal_on_connect(self):
        """_connect() enables WAL mode."""
        async def _check():
            conn = await self.client._connect()
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            await conn.close()
            return row[0]

        mode = run_async(_check())
        self.assertEqual(mode, "wal")

    def test_init_priority_table(self):
        """init_priority_table() succeeds."""
        result = run_async(self.client.init_priority_table())
        self.assertTrue(result)

    # --- Priority send tests ---

    def test_send_priority_returns_id(self):
        """send() with priority returns message ID."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        msg_id = run_async(self.client.send("bob", "high priority", priority=Priority.HIGH))
        self.assertIsInstance(msg_id, int)
        self.assertGreater(msg_id, 0)

    def test_send_priority_low_creates_message(self):
        """send() with LOW priority stores message with correct priority."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        msg_id = run_async(self.client.send("bob", "low prio", priority=Priority.LOW))
        self.assertGreater(msg_id, 0)

        async def _check():
            conn = await self.client._connect()
            cursor = await conn.execute("SELECT priority FROM messages WHERE id = ?", (msg_id,))
            row = await cursor.fetchone()
            await conn.close()
            return row[0]
        stored = run_async(_check())
        self.assertEqual(stored, 1)  # LOW = 1

    def test_send_priority_critical_creates_message(self):
        """send() with CRITICAL priority stores message with correct priority."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        msg_id = run_async(self.client.send("bob", "critical!", priority=Priority.CRITICAL))
        self.assertGreater(msg_id, 0)

        async def _check():
            conn = await self.client._connect()
            cursor = await conn.execute("SELECT priority FROM messages WHERE id = ?", (msg_id,))
            row = await cursor.fetchone()
            await conn.close()
            return row[0]
        stored = run_async(_check())
        self.assertEqual(stored, 4)  # CRITICAL = 4

    def test_send_invalid_priority_too_low_raises(self):
        """send() with priority < 1 raises ValueError."""
        run_async(self.client.init_priority_table())
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "bad", priority=0))
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "bad", priority=-1))

    def test_send_invalid_priority_too_high_raises(self):
        """send() with priority > 4 raises ValueError."""
        run_async(self.client.init_priority_table())
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "bad", priority=5))
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "bad", priority=999))

    def test_send_priority_ttl_nan_raises(self):
        """send() with NaN ttl_seconds raises ValueError."""
        run_async(self.client.init_priority_table())
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "nan ttl", ttl_seconds=float("nan")))

    def test_send_priority_ttl_inf_raises(self):
        """send() with inf ttl_seconds raises ValueError."""
        run_async(self.client.init_priority_table())
        with self.assertRaises(ValueError):
            run_async(self.client.send("bob", "inf ttl", ttl_seconds=float("inf")))

    # --- Priority recv tests ---

    def test_recv_priority_ordering_highest_first(self):
        """recv() with priority_aware returns highest priority messages first."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "normal", priority=Priority.NORMAL))
        run_async(self.client.send("bob", "low", priority=Priority.LOW))
        run_async(self.client.send("bob", "high", priority=Priority.HIGH))
        run_async(self.client.send("bob", "critical", priority=Priority.CRITICAL))

        # Use a second client for recv
        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        messages = run_async(bob.recv(wait=1, priority_aware=True))
        bodies = [m["body"] for m in messages]
        # Check critical appears before low
        crit_idx = bodies.index("critical")
        low_idx = bodies.index("low")
        self.assertLess(crit_idx, low_idx, "critical should appear before low")

    def test_recv_chronological_when_priority_aware_off(self):
        """recv(priority_aware=False) returns messages in chronological order."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "first", priority=Priority.CRITICAL))
        run_async(self.client.send("bob", "second", priority=Priority.LOW))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        messages = run_async(bob.recv(wait=1, priority_aware=False))
        bodies = [m["body"] for m in messages]
        self.assertEqual(bodies[0], "first")
        self.assertEqual(bodies[1], "second")

    def test_recv_by_priority_filters_correctly(self):
        """recv_by_priority() returns only messages with specified priority."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "normal msg", priority=Priority.NORMAL))
        run_async(self.client.send("bob", "high msg", priority=Priority.HIGH))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        high_msgs = run_async(bob.recv_by_priority(Priority.HIGH, wait=1))
        self.assertEqual(len(high_msgs), 1)
        self.assertEqual(high_msgs[0]["body"], "high msg")
        self.assertEqual(high_msgs[0]["priority"], Priority.HIGH)

    def test_recv_by_priority_returns_empty_when_no_match(self):
        """recv_by_priority() returns empty list when no messages match priority."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "low msg", priority=Priority.LOW))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        critical_msgs = run_async(bob.recv_by_priority(Priority.CRITICAL, wait=0))
        self.assertEqual(len(critical_msgs), 0)

    def test_recv_above_priority_returns_messages(self):
        """recv_above_priority() returns messages with priority >= min."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "low", priority=Priority.LOW))
        run_async(self.client.send("bob", "normal", priority=Priority.NORMAL))
        run_async(self.client.send("bob", "high", priority=Priority.HIGH))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        above_high = run_async(bob.recv_above_priority(Priority.HIGH, wait=1))
        bodies = {m["body"] for m in above_high}
        self.assertIn("high", bodies)
        self.assertNotIn("low", bodies)
        self.assertNotIn("normal", bodies)

    def test_recv_above_priority_returns_empty_for_high_min(self):
        """recv_above_priority() returns empty when no messages meet min."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "low", priority=Priority.LOW))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        above_critical = run_async(bob.recv_above_priority(Priority.CRITICAL, wait=0))
        self.assertEqual(len(above_critical), 0)

    # --- Priority stats tests ---

    def test_get_priority_stats_returns_dict(self):
        """get_priority_stats() returns distribution dict."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "normal msg", priority=Priority.NORMAL))
        run_async(self.client.send("bob", "high msg", priority=Priority.HIGH))

        stats = run_async(self.client.get_priority_stats())
        self.assertIsInstance(stats, dict)
        self.assertIn("NORMAL", stats)
        self.assertIn("HIGH", stats)
        self.assertEqual(stats["NORMAL"], 1)
        self.assertEqual(stats["HIGH"], 1)

    def test_get_priority_stats_empty(self):
        """get_priority_stats() returns empty dict when no messages."""
        run_async(self.client.init_priority_table())
        stats = run_async(self.client.get_priority_stats())
        self.assertEqual(stats, {})

    def test_get_priority_stats_by_agent(self):
        """get_priority_stats_by_agent() returns per-agent distribution."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "important", priority=Priority.HIGH))
        run_async(self.client.send("bob", "critical", priority=Priority.CRITICAL))

        stats = run_async(self.client.get_priority_stats_by_agent("alice"))
        self.assertIsInstance(stats, dict)
        self.assertIn("HIGH", stats)
        self.assertIn("CRITICAL", stats)

    def test_get_priority_stats_by_agent_empty(self):
        """get_priority_stats_by_agent() returns empty dict for unknown agent."""
        run_async(self.client.init_priority_table())
        stats = run_async(self.client.get_priority_stats_by_agent("nobody"))
        self.assertEqual(stats, {})

    # --- Convenience methods ---

    def test_get_critical_messages(self):
        """get_critical_messages() returns critical priority messages."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "critical msg", priority=Priority.CRITICAL))
        run_async(self.client.send("bob", "normal msg", priority=Priority.NORMAL))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        criticals = run_async(bob.get_critical_messages())
        bodies = [m["body"] for m in criticals]
        self.assertIn("critical msg", bodies)
        self.assertNotIn("normal msg", bodies)

    def test_get_high_priority_messages(self):
        """get_high_priority_messages() returns high+critical messages."""
        run_async(self.client.init_priority_table())
        from a2a_priority import Priority
        run_async(self.client.send("bob", "critical msg", priority=Priority.CRITICAL))
        run_async(self.client.send("bob", "high msg", priority=Priority.HIGH))
        run_async(self.client.send("bob", "low msg", priority=Priority.LOW))

        from a2a_priority_async import PriorityClientAsync
        bob = PriorityClientAsync(self.project, "bob")
        high_msgs = run_async(bob.get_high_priority_messages())
        bodies = [m["body"] for m in high_msgs]
        self.assertIn("critical msg", bodies)
        self.assertIn("high msg", bodies)
        self.assertNotIn("low msg", bodies)

    # --- Mark read ---

    def test_mark_read(self):
        """mark_read() marks a message as read."""
        run_async(self.client.init_priority_table())
        msg_id = run_async(self.client.send("bob", "readable msg"))
        self.assertGreater(msg_id, 0)
        result = run_async(self.client.mark_read(msg_id))
        self.assertTrue(result)

        async def _check():
            conn = await self.client._connect()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM reads WHERE message_id = ? AND agent_id = ?",
                (msg_id, "alice"),
            )
            row = await cursor.fetchone()
            await conn.close()
            return row[0]
        count = run_async(_check())
        self.assertEqual(count, 1)

    def test_mark_read_idempotent(self):
        """mark_read() called twice does not raise."""
        run_async(self.client.init_priority_table())
        msg_id = run_async(self.client.send("bob", "idempotent"))
        run_async(self.client.mark_read(msg_id))
        # Second call should not raise
        result = run_async(self.client.mark_read(msg_id))
        self.assertTrue(result)


class TestPriorityClientAsyncNoAioSQLite(unittest.TestCase):
    """Test PriorityClientAsync raises ImportError without aiosqlite."""

    @unittest.skipIf(HAS_AIOSQLITE, "aiosqlite IS available — skip ImportError test")
    def test_raises_import_error_without_aiosqlite(self):
        """PriorityClientAsync raises ImportError when aiosqlite is missing."""
        from a2a_priority_async import PriorityClientAsync
        with self.assertRaises(ImportError):
            PriorityClientAsync("project", "agent")


@unittest.skipUnless(HAS_AIOSQLITE, SKIP_MSG)
class TestRoutingClientAsync(unittest.TestCase):
    """Tests for RoutingClientAsync."""

    @classmethod
    def setUpClass(cls):
        cls.test_home = tempfile.mkdtemp()
        cls.original_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.test_home

    @classmethod
    def tearDownClass(cls):
        if cls.original_home:
            os.environ["HOME"] = cls.original_home

    def setUp(self):
        from a2a_routing_async import RoutingClientAsync
        self.project = f"routing-async-{id(self)}"
        project_dir = Path(self.test_home) / ".a2a" / self.project
        project_dir.mkdir(parents=True, exist_ok=True)
        _setup_db(project_dir)
        # Add priority column needed by recv_with_routing / apply_routing
        import sqlite3
        conn = make_connection(project_dir / "database.db")
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN priority INTEGER DEFAULT 2")
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
        finally:
            conn.close()
        self.client = RoutingClientAsync(self.project, "alice")

    def test_instantiation_succeeds(self):
        """RoutingClientAsync instantiates when aiosqlite present."""
        self.assertIsNotNone(self.client)

    def test_starts_with_no_rules(self):
        """RoutingClientAsync starts with empty rules list."""
        self.assertEqual(self.client.rules, [])

    def test_init_routing_table(self):
        """init_routing_table() succeeds."""
        result = run_async(self.client.init_routing_table())
        self.assertTrue(result)

    def test_wal_on_connect(self):
        """_connect() enables WAL mode."""
        async def _check():
            conn = await self.client._connect()
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            await conn.close()
            return row[0]

        mode = run_async(_check())
        self.assertEqual(mode, "wal")

    # --- Rule CRUD tests ---

    def test_add_rule_roundtrip(self):
        """add_rule() then get_rules() returns the rule."""
        from a2a_routing import RoutingRule, RoutingAction
        from a2a_routing_async import RoutingClientAsync
        run_async(self.client.init_routing_table())
        rule = RoutingRule("alert-rule", RoutingAction.DELIVER, match_content="urgent")
        added = run_async(self.client.add_rule(rule))
        self.assertTrue(added)
        rules = run_async(self.client.get_rules())
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].name, "alert-rule")

    def test_add_rule_updates_inmemory_list(self):
        """add_rule() appends rule to in-memory self.rules."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        self.assertEqual(len(self.client.rules), 0)
        rule = RoutingRule("r1", RoutingAction.DELIVER)
        run_async(self.client.add_rule(rule))
        self.assertEqual(len(self.client.rules), 1)
        self.assertEqual(self.client.rules[0].name, "r1")

    def test_add_multiple_rules(self):
        """Multiple rules can be added and retrieved."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("r1", RoutingAction.DELIVER)))
        run_async(self.client.add_rule(RoutingRule("r2", RoutingAction.FORWARD, forward_to="bob")))
        rules = run_async(self.client.get_rules())
        names = {r.name for r in rules}
        self.assertIn("r1", names)
        self.assertIn("r2", names)

    def test_get_rules_empty_when_no_rules(self):
        """get_rules() returns empty list when no rules defined."""
        from a2a_routing_async import RoutingClientAsync
        run_async(self.client.init_routing_table())
        rules = run_async(self.client.get_rules())
        self.assertEqual(rules, [])

    def test_disable_rule(self):
        """disable_rule() marks rule as disabled."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("tog", RoutingAction.DELIVER)))
        result = run_async(self.client.disable_rule("tog"))
        self.assertTrue(result)
        rules = run_async(self.client.get_rules())
        self.assertFalse(rules[0].enabled)

    def test_enable_rule(self):
        """enable_rule() re-enables a disabled rule."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("tog", RoutingAction.DELIVER)))
        run_async(self.client.disable_rule("tog"))
        result = run_async(self.client.enable_rule("tog"))
        self.assertTrue(result)
        rules = run_async(self.client.get_rules())
        self.assertTrue(rules[0].enabled)

    def test_delete_rule(self):
        """delete_rule() removes rule from database."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("del-me", RoutingAction.DISCARD)))
        result = run_async(self.client.delete_rule("del-me"))
        self.assertTrue(result)
        rules = run_async(self.client.get_rules())
        self.assertEqual(len(rules), 0)

    def test_disable_nonexistent_rule_still_succeeds(self):
        """disable_rule() on nonexistent rule does not raise."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        result = run_async(self.client.disable_rule("no-such-rule"))
        self.assertTrue(result)

    def test_delete_nonexistent_rule_still_succeeds(self):
        """delete_rule() on nonexistent rule does not raise."""
        run_async(self.client.init_routing_table())
        result = run_async(self.client.delete_rule("no-such-rule"))
        self.assertTrue(result)

    # --- Rule matching tests ---

    def test_rule_match_by_sender(self):
        """Rule matching filters by sender correctly."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("from-bob", RoutingAction.DELIVER, match_sender="bob")
        self.assertTrue(rule.matches({"sender": "bob", "body": "hi"}))
        self.assertFalse(rule.matches({"sender": "alice", "body": "hi"}))

    def test_rule_match_by_content(self):
        """Rule matching filters by content pattern."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("urgent", RoutingAction.DELIVER, match_content="urgent")
        self.assertTrue(rule.matches({"sender": "alice", "body": "this is urgent"}))
        self.assertFalse(rule.matches({"sender": "alice", "body": "normal message"}))

    def test_rule_match_by_priority(self):
        """Rule matching filters by minimum priority."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("high-only", RoutingAction.DELIVER, match_priority=3)
        self.assertTrue(rule.matches({"sender": "alice", "priority": 4, "body": ""}))
        self.assertTrue(rule.matches({"sender": "alice", "priority": 3, "body": ""}))
        self.assertFalse(rule.matches({"sender": "alice", "priority": 2, "body": ""}))

    def test_rule_match_by_thread(self):
        """Rule matching filters by thread ID."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("thread-only", RoutingAction.DELIVER, match_thread="t-42")
        self.assertTrue(rule.matches({"sender": "alice", "thread_id": "t-42", "body": ""}))
        self.assertFalse(rule.matches({"sender": "alice", "thread_id": "other", "body": ""}))

    def test_disabled_rule_does_not_match(self):
        """Disabled rule returns False for matches()."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("disabled", RoutingAction.DELIVER, match_content="anything", enabled=False)
        self.assertFalse(rule.matches({"sender": "alice", "body": "anything"}))

    def test_rule_all_criteria_must_match(self):
        """Rule requires ALL specified criteria to match (AND logic)."""
        from a2a_routing import RoutingRule, RoutingAction
        rule = RoutingRule("strict", RoutingAction.DELIVER,
                          match_sender="alice", match_content="deploy")
        self.assertTrue(rule.matches({"sender": "alice", "body": "deploy now"}))
        self.assertFalse(rule.matches({"sender": "bob", "body": "deploy now"}))
        self.assertFalse(rule.matches({"sender": "alice", "body": "hello"}))

    # --- recv_with_routing tests ---

    def test_recv_with_routing_deliver(self):
        """recv_with_routing() routes unmatched messages to deliver."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        rule = RoutingRule("catch-all", RoutingAction.DELIVER, match_content="hello")
        run_async(self.client.add_rule(rule))

        # Send a matching message
        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", self.client.agent_id, "hello world", time.time()),
        )
        conn.commit()
        conn.close()

        routed = run_async(self.client.recv_with_routing(wait=1))
        self.assertIn("deliver", routed)
        self.assertGreaterEqual(len(routed["deliver"]), 1)

    def test_recv_with_routing_no_match_delivers_default(self):
        """Unmatched messages default to deliver bucket."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        # Rule that won't match
        rule = RoutingRule("only-urgent", RoutingAction.DISCARD, match_content="URGENT")
        run_async(self.client.add_rule(rule))

        # Send a non-matching message
        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", self.client.agent_id, "normal message", time.time()),
        )
        conn.commit()
        conn.close()

        routed = run_async(self.client.recv_with_routing(wait=1))
        self.assertIn("deliver", routed)
        self.assertGreaterEqual(len(routed["deliver"]), 1)

    def test_recv_with_routing_discard_action(self):
        """Discard action routes messages to discard bucket."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        rule = RoutingRule("trash", RoutingAction.DISCARD, match_content="spam")
        run_async(self.client.add_rule(rule))

        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", self.client.agent_id, "this is spam", time.time()),
        )
        conn.commit()
        conn.close()

        routed = run_async(self.client.recv_with_routing(wait=1))
        self.assertIn("discard", routed)
        self.assertGreaterEqual(len(routed["discard"]), 1)

    def test_recv_with_routing_does_not_raise_without_rules(self):
        """recv_with_routing() works with no rules defined."""
        run_async(self.client.init_routing_table())
        routed = run_async(self.client.recv_with_routing(wait=0))
        self.assertIn("deliver", routed)
        self.assertIn("discard", routed)
        self.assertIn("forward", routed)
        self.assertIn("queue", routed)
        self.assertIn("escalate", routed)

    # --- apply_routing tests ---

    def test_apply_routing_forward(self):
        """apply_routing() forwards messages that are routed as forward."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        import sqlite3, time

        # Create a forward action
        routed = {
            "forward": [{
                "message": {"id": 1, "body": "forward me", "priority": 2, "thread_id": None},
                "rule": "fwd-rule",
                "forward_to": "bob",
            }],
            "deliver": [], "discard": [], "queue": [], "escalate": [],
        }
        result = run_async(self.client.apply_routing(routed))
        self.assertTrue(result)

        # Check a forwarded message was created
        conn = make_connection(self.client.db_path)
        cursor = conn.execute("SELECT body FROM messages WHERE body LIKE '[Forwarded]%'")
        rows = cursor.fetchall()
        conn.close()
        self.assertGreater(len(rows), 0)
        self.assertIn("forward me", rows[0][0])

    def test_apply_routing_discard(self):
        """apply_routing() marks discarded messages as read."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        import time

        # Insert a message first
        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            ("bob", self.client.agent_id, "discard me", time.time()),
        )
        conn.commit()
        cursor = conn.execute("SELECT id FROM messages WHERE body = 'discard me'")
        msg_id = cursor.fetchone()[0]
        conn.close()

        routed = {
            "discard": [{
                "message": {"id": msg_id, "body": "discard me"},
                "rule": "trash-rule",
                "forward_to": None,
            }],
            "deliver": [], "forward": [], "queue": [], "escalate": [],
        }
        result = run_async(self.client.apply_routing(routed))
        self.assertTrue(result)

        # Check message was marked as read
        conn = make_connection(self.client.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM reads WHERE message_id = ? AND agent_id = ?",
            (msg_id, self.client.agent_id),
        )
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_apply_routing_empty_no_error(self):
        """apply_routing() with empty routing dict does not raise."""
        run_async(self.client.init_routing_table())
        routed = {"deliver": [], "forward": [], "discard": [], "queue": [], "escalate": []}
        result = run_async(self.client.apply_routing(routed))
        self.assertTrue(result)

    # --- get_routing_stats tests ---

    def test_get_routing_stats_all_fields(self):
        """get_routing_stats() returns all expected fields."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("r1", RoutingAction.DELIVER)))
        run_async(self.client.add_rule(RoutingRule("r2", RoutingAction.FORWARD, forward_to="bob")))
        run_async(self.client.disable_rule("r2"))

        stats = run_async(self.client.get_routing_stats())
        self.assertIn("total_rules", stats)
        self.assertIn("enabled_rules", stats)
        self.assertIn("disabled_rules", stats)
        self.assertIn("by_action", stats)
        self.assertEqual(stats["total_rules"], 2)
        self.assertEqual(stats["enabled_rules"], 1)
        self.assertEqual(stats["disabled_rules"], 1)

    def test_get_routing_stats_empty(self):
        """get_routing_stats() returns zeros when no rules."""
        run_async(self.client.init_routing_table())
        stats = run_async(self.client.get_routing_stats())
        self.assertEqual(stats["total_rules"], 0)
        self.assertEqual(stats["enabled_rules"], 0)
        self.assertEqual(stats["disabled_rules"], 0)
        self.assertEqual(stats["by_action"], {})

    # --- Edge case: recv_with_routing with include_self ---

    def test_recv_with_routing_include_self(self):
        """recv_with_routing(include_self=True) includes own messages."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("catch", RoutingAction.DELIVER)))

        import time
        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            (self.client.agent_id, self.client.agent_id, "self msg", time.time()),
        )
        conn.commit()
        conn.close()

        routed = run_async(self.client.recv_with_routing(wait=1, include_self=True))
        delivered = [item["message"]["body"] for item in routed["deliver"]]
        self.assertIn("self msg", delivered)

    def test_recv_with_routing_excludes_self_by_default(self):
        """recv_with_routing() excludes own messages by default."""
        from a2a_routing import RoutingRule, RoutingAction
        run_async(self.client.init_routing_table())
        run_async(self.client.add_rule(RoutingRule("catch", RoutingAction.DELIVER)))

        import time
        conn = make_connection(self.client.db_path)
        conn.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
            (self.client.agent_id, self.client.agent_id, "hidden self msg", time.time()),
        )
        conn.commit()
        conn.close()

        routed = run_async(self.client.recv_with_routing(wait=1, include_self=False))
        delivered = [item["message"]["body"] for item in routed["deliver"]]
        self.assertNotIn("hidden self msg", delivered)


class TestRoutingClientAsyncNoAioSQLite(unittest.TestCase):
    """Test RoutingClientAsync raises ImportError without aiosqlite."""

    @unittest.skipIf(HAS_AIOSQLITE, "aiosqlite IS available — skip ImportError test")
    def test_raises_import_error_without_aiosqlite(self):
        """RoutingClientAsync raises ImportError when aiosqlite is missing."""
        from a2a_routing_async import RoutingClientAsync
        with self.assertRaises(ImportError):
            RoutingClientAsync("project", "agent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
