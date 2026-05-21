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
    conn = sqlite3.connect(str(db_path))
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

    def test_recv_cleans_up_expired_messages(self):
        """recv() triggers TTL cleanup so expired messages are not returned."""
        run_async(self.alice.send("bob", "will expire", ttl_seconds=0))
        messages = run_async(self.bob.recv(wait=1))
        bodies = [m["body"] for m in messages]
        self.assertNotIn("will expire", bodies)

    def test_peek_cleans_up_expired_messages(self):
        """peek() triggers TTL cleanup so expired messages don't appear."""
        run_async(self.alice.send("bob", "ttl will vanish", ttl_seconds=0))
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
