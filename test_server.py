#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for a2a_server.py — REST API server."""

import http.client
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from a2a_server import run_server


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


def _find_free_port():
    """Find an available TCP port."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestA2ARestServer(unittest.TestCase):
    """Integration tests for the a2a REST API server."""

    @classmethod
    def setUpClass(cls):
        """Start REST server in a background thread with a fresh database."""
        cls.test_home = tempfile.mkdtemp()
        cls.original_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.test_home

        cls.project = "test-rest-api"
        cls.port = _find_free_port()

        # Create database
        db_dir = Path(cls.test_home) / ".a2a" / cls.project
        db_dir.mkdir(parents=True, exist_ok=True)
        cls.db_path = db_dir / "database.db"
        conn = sqlite3.connect(str(cls.db_path))
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

        # Start server thread
        cls.server_thread = threading.Thread(
            target=run_server,
            args=(cls.project, "127.0.0.1", cls.port),
            daemon=True,
        )
        cls.server_thread.start()
        # Wait for server to start
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        """Restore HOME."""
        if cls.original_home:
            os.environ["HOME"] = cls.original_home

    def _get(self, path):
        """Make a GET request and return (status, body_dict)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        conn.close()
        return resp.status, body

    def _post(self, path, data):
        """Make a POST request and return (status, body_dict)."""
        payload = json.dumps(data).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST", path, payload,
            {"Content-Type": "application/json", "Content-Length": str(len(payload))}
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        conn.close()
        return resp.status, body

    # --- /health ---

    def test_health_returns_200(self):
        """GET /health returns 200."""
        status, body = self._get("/health")
        self.assertEqual(status, 200)

    def test_health_body(self):
        """GET /health returns {status: ok}."""
        _, body = self._get("/health")
        self.assertEqual(body, {"status": "ok"})

    # --- /peers ---

    def test_peers_returns_200(self):
        """GET /peers returns 200."""
        status, body = self._get("/peers")
        self.assertEqual(status, 200)

    def test_peers_has_list(self):
        """GET /peers returns peers list."""
        _, body = self._get("/peers")
        self.assertIn("peers", body)
        self.assertIsInstance(body["peers"], list)

    def test_peers_contains_agents(self):
        """GET /peers includes registered agents."""
        _, body = self._get("/peers")
        ids = {p["id"] for p in body["peers"]}
        self.assertIn("alice", ids)
        self.assertIn("bob", ids)

    # --- POST /send ---

    def test_send_direct_message(self):
        """POST /send sends a direct message."""
        status, body = self._post("/send", {"to": "bob", "message": "Hello Bob"})
        self.assertEqual(status, 200)
        self.assertIn("message_id", body)
        self.assertGreater(body["message_id"], 0)
        self.assertEqual(body["status"], "sent")

    def test_send_broadcast(self):
        """POST /send with to=all sends broadcast."""
        status, body = self._post("/send", {"to": "all", "message": "Broadcast!"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "sent")

    def test_send_missing_to_returns_400(self):
        """POST /send without 'to' returns 400."""
        status, body = self._post("/send", {"message": "Missing to"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_send_missing_message_returns_400(self):
        """POST /send without 'message' returns 400."""
        status, body = self._post("/send", {"to": "bob"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_send_with_star_recipient(self):
        """POST /send with to=* is treated as broadcast."""
        status, body = self._post("/send", {"to": "*", "message": "Star broadcast"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "sent")

    # --- GET /messages ---

    def test_messages_returns_200(self):
        """GET /messages returns 200."""
        status, _ = self._get("/messages")
        self.assertEqual(status, 200)

    def test_messages_has_list(self):
        """GET /messages returns messages list."""
        _, body = self._get("/messages")
        self.assertIn("messages", body)
        self.assertIsInstance(body["messages"], list)

    def test_messages_contains_sent_messages(self):
        """GET /messages shows messages we sent."""
        self._post("/send", {"to": "bob", "message": "Test peek message"})
        _, body = self._get("/messages?limit=50")
        bodies = [m["body"] for m in body["messages"]]
        self.assertIn("Test peek message", bodies)

    # --- POST /recv ---

    def test_recv_returns_200(self):
        """POST /recv returns 200."""
        status, body = self._post("/recv", {"agent": "bob"})
        self.assertEqual(status, 200)

    def test_recv_has_messages_key(self):
        """POST /recv returns messages key."""
        _, body = self._post("/recv", {"agent": "bob"})
        self.assertIn("messages", body)

    def test_recv_gets_direct_message(self):
        """POST /recv retrieves direct messages for agent."""
        unique_msg = f"direct-recv-{time.time()}"
        self._post("/send", {"to": "carol", "message": unique_msg})
        _, body = self._post("/recv", {"agent": "carol"})
        received_bodies = [m["body"] for m in body["messages"]]
        self.assertIn(unique_msg, received_bodies)

    def test_recv_limit_caps_messages(self):
        """POST /recv with limit returns at most N messages."""
        for i in range(3):
            self._post("/send", {"to": "dave", "message": f"limit-msg-{i}"})
        _, body = self._post("/recv", {"agent": "dave", "limit": 2})
        self.assertLessEqual(len(body["messages"]), 2)

    def test_search_with_limit(self):
        """GET /search with limit caps results."""
        prefix = f"limit-search-{int(time.time())}"
        for i in range(3):
            self._post("/send", {"to": "all", "message": f"{prefix}-{i}"})
        _, body = self._get(f"/search?q={prefix}&limit=2")
        self.assertLessEqual(len(body.get("results", [])), 2)

    # --- GET /search ---

    def test_search_returns_200(self):
        """GET /search with query returns 200."""
        status, _ = self._get("/search?q=hello")
        self.assertEqual(status, 200)

    def test_search_missing_q_returns_400(self):
        """GET /search without q parameter returns 400."""
        status, body = self._get("/search")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_search_finds_message(self):
        """GET /search finds messages by keyword."""
        unique_keyword = f"searchable-{int(time.time())}"
        self._post("/send", {"to": "all", "message": f"Test {unique_keyword} content"})
        _, body = self._get(f"/search?q={unique_keyword}")
        self.assertIn("results", body)
        found = any(unique_keyword in m["body"] for m in body["results"])
        self.assertTrue(found)

    def test_search_returns_query_echo(self):
        """GET /search echoes the query in response."""
        _, body = self._get("/search?q=findme")
        self.assertEqual(body.get("query"), "findme")

    # --- GET /thread ---

    def test_thread_returns_400_without_id(self):
        """GET /thread without id returns 400."""
        status, body = self._get("/thread")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_thread_returns_empty_for_unknown_thread(self):
        """GET /thread with unknown id returns empty messages."""
        _, body = self._get("/thread?id=nonexistent-thread-123")
        self.assertIn("messages", body)
        self.assertEqual(body["messages"], [])

    # --- GET /stats ---

    def test_stats_returns_200(self):
        """GET /stats returns 200."""
        status, _ = self._get("/stats")
        self.assertEqual(status, 200)

    def test_stats_has_required_fields(self):
        """GET /stats returns all required stats fields."""
        _, body = self._get("/stats")
        self.assertIn("messages", body)
        self.assertIn("broadcasts", body)
        self.assertIn("agents", body)

    def test_stats_counts_agents(self):
        """GET /stats counts registered agents."""
        _, body = self._get("/stats")
        self.assertGreaterEqual(body["agents"], 2)

    # --- GET /agent ---

    def test_agent_returns_status(self):
        """GET /agent returns agent status."""
        _, body = self._get("/agent?id=alice")
        self.assertEqual(body.get("status"), "active")
        self.assertEqual(body.get("agent"), "alice")

    def test_agent_missing_id_returns_400(self):
        """GET /agent without id returns 400."""
        status, body = self._get("/agent")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_agent_not_found_returns_404(self):
        """GET /agent with unknown id returns 404."""
        status, body = self._get("/agent?id=nobody")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    # --- POST /status ---

    def test_set_status_returns_200(self):
        """POST /status returns 200."""
        status, body = self._post("/status", {"agent": "alice", "status": "idle"})
        self.assertEqual(status, 200)

    def test_set_status_updates_agent(self):
        """POST /status updates agent status."""
        self._post("/status", {"agent": "bob", "status": "done"})
        _, body = self._get("/agent?id=bob")
        self.assertEqual(body["status"], "done")

    def test_set_status_missing_status_returns_400(self):
        """POST /status without status returns 400."""
        status, body = self._post("/status", {"agent": "alice"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    # --- /register and /unregister ---

    def test_register_creates_agent(self):
        """POST /register adds agent to the bus."""
        status, body = self._post("/register", {"agent_id": "new-bot", "role": "tester"})
        self.assertEqual(status, 200)
        self.assertEqual(body["agent_id"], "new-bot")
        self.assertEqual(body["status"], "active")

    def test_register_missing_agent_id_returns_400(self):
        """POST /register without agent_id returns 400."""
        status, body = self._post("/register", {"role": "tester"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_unregister_removes_agent(self):
        """POST /unregister removes agent from bus."""
        self._post("/register", {"agent_id": "to-remove", "role": "temp"})
        status, body = self._post("/unregister", {"agent_id": "to-remove"})
        self.assertEqual(status, 200)
        self.assertTrue(body["unregistered"])

    def test_unregister_missing_agent_id_returns_400(self):
        """POST /unregister without agent_id returns 400."""
        status, body = self._post("/unregister", {})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    # --- /send with thread_id ---

    def test_send_with_thread_id(self):
        """POST /send with thread_id stores thread on message."""
        status, body = self._post("/send", {
            "to": "alice",
            "message": "threaded message",
            "thread_id": "t-42",
        })
        self.assertEqual(status, 200)
        self.assertIn("message_id", body)

    # --- Edge cases ---

    def test_send_with_ttl(self):
        """POST /send with ttl_seconds stores TTL on message."""
        status, body = self._post("/send", {
            "to": "alice",
            "message": "ttl test",
            "ttl_seconds": 3600,
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "sent")

    def test_recv_limit_zero_returns_empty(self):
        """POST /recv with limit=0 returns empty messages list."""
        self._post("/send", {"to": "limit-zero-agent", "message": "should not appear"})
        status, body = self._post("/recv", {"agent": "limit-zero-agent", "limit": 0})
        self.assertEqual(status, 200)
        self.assertEqual(body["messages"], [])

    def test_peek_limit_zero_returns_empty(self):
        """GET /messages with limit=0 returns empty messages list."""
        _, body = self._get("/messages?limit=0")
        self.assertEqual(body["messages"], [])

    def test_stats_all_fields_present(self):
        """GET /stats returns all five required fields."""
        _, body = self._get("/stats")
        self.assertIn("messages", body)
        self.assertIn("broadcasts", body)
        self.assertIn("direct", body)
        self.assertIn("threads", body)
        self.assertIn("agents", body)
        # Counts should be non-negative integers
        for field in ("messages", "broadcasts", "direct", "threads", "agents"):
            self.assertIsInstance(body[field], int)
            self.assertGreaterEqual(body[field], 0)

    def test_recv_with_invalid_json_returns_400(self):
        """POST /recv with invalid JSON body returns 400."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/recv", b"not valid json{{{",
                     {"Content-Type": "application/json", "Content-Length": "16"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        conn.close()
        self.assertEqual(resp.status, 400)
        self.assertIn("error", body)

    def test_send_with_empty_message_returns_400(self):
        """POST /send with empty message string returns 400."""
        status, body = self._post("/send", {"to": "bob", "message": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_unknown_get_route_returns_404(self):
        """GET to unknown path returns 404."""
        status, body = self._get("/nonexistent")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_unknown_post_route_returns_404(self):
        """POST to unknown path returns 404."""
        status, body = self._post("/nonexistent", {})
        self.assertEqual(status, 404)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
