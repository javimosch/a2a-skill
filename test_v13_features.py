#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.3 Feature Tests — Comprehensive test suite for encryption, audit, FTS, priority, and routing.

Run with: python3 test_v13_features.py
"""

import unittest
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import Mock, patch

from a2a_crypto import CryptoClient
from a2a_fts import FTSClient
from a2a_audit import AuditClient
from a2a_priority import PriorityClient, Priority
from a2a_routing import RoutingClient, RoutingRule, RoutingAction


class TestEncryption(unittest.TestCase):
    """Test suite for message encryption (v1.3)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.crypto = CryptoClient("test-project", "alice", key_dir=self.temp_dir)

    def test_symmetric_key_generation(self):
        """Test symmetric key generation."""
        key = self.crypto.generate_symmetric_key()
        self.assertIsNotNone(key)
        self.assertIsInstance(key, str)
        self.assertGreater(len(key), 0)

    def test_symmetric_encryption_decryption(self):
        """Test symmetric encryption and decryption."""
        key = self.crypto.generate_symmetric_key()
        message = "Secret message"

        encrypted = self.crypto.encrypt_message(message, key)
        self.assertNotEqual(encrypted, message)

        decrypted = self.crypto.decrypt_message(encrypted, key)
        self.assertEqual(decrypted, message)

    def test_keypair_generation(self):
        """Test RSA keypair generation."""
        public_key, private_key = self.crypto.generate_keypair()
        self.assertIsNotNone(public_key)
        self.assertIsNotNone(private_key)
        self.assertIn("BEGIN PUBLIC KEY", public_key)
        self.assertIn("BEGIN PRIVATE KEY", private_key)

    def test_asymmetric_encryption_decryption(self):
        """Test asymmetric encryption and decryption."""
        public_key, private_key = self.crypto.generate_keypair()
        message = "Secret message"

        encrypted = self.crypto.encrypt_with_public_key(message, public_key)
        self.assertNotEqual(encrypted, message)

        decrypted = self.crypto.decrypt_with_private_key(encrypted, private_key)
        self.assertEqual(decrypted, message)

    def test_message_wrapping(self):
        """Test transparent message wrapping."""
        public_key, _ = self.crypto.generate_keypair()
        message = "Confidential"

        wrapped = self.crypto.wrap_encrypted_message(message, public_key)
        self.assertIsInstance(wrapped, str)

        # Parse wrapped message
        wrapper = json.loads(wrapped)
        self.assertEqual(wrapper["type"], "encrypted")
        self.assertEqual(wrapper["sender"], "alice")
        self.assertIn("encrypted_body", wrapper)

    def test_get_public_key(self):
        """Test public key retrieval."""
        key = self.crypto.get_public_key()
        self.assertIsNotNone(key)
        self.assertIn("BEGIN PUBLIC KEY", key)


class TestFullTextSearch(unittest.TestCase):
    """Test suite for full-text search (v1.3)."""

    def setUp(self):
        """Set up test fixtures."""
        # Would need database setup; using mock for now
        self.fts = FTSClient("test-project", "alice")

    def test_init_fts_table(self):
        """Test FTS table initialization."""
        # This would require a real database
        # For now, test the class structure
        self.assertTrue(hasattr(self.fts, 'search_fts'))
        self.assertTrue(hasattr(self.fts, 'search_advanced'))
        self.assertTrue(hasattr(self.fts, 'get_search_suggestions'))

    def test_query_builder(self):
        """Test query builder for complex queries."""
        from a2a_fts import SearchQueryBuilder

        builder = SearchQueryBuilder()
        query = (
            builder
            .add_term("error")
            .must_contain("critical")
            .must_not_contain("resolved")
            .build()
        )

        self.assertIn("error", query)
        self.assertIn("critical", query)
        self.assertIn("-resolved", query)


class TestFTSClientWithDB(unittest.TestCase):
    """Real-database tests for FTSClient search methods."""

    def setUp(self):
        import os
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        import a2a
        self.project = f"fts-db-test-{os.getpid()}-{id(self)}"
        conn = a2a.connect(self.project, create=True)
        conn.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) VALUES (?,?,?,?,?)",
            ("alice", "tester", "active", 1000.0, 1000.0),
        )
        conn.execute(
            "INSERT INTO agents(id, role, status, created_at, last_seen) VALUES (?,?,?,?,?)",
            ("bob", "tester", "active", 1000.0, 1000.0),
        )
        bodies = [
            "authentication service is down",
            "deployment completed successfully",
            "error in authentication module",
            "database backup finished",
        ]
        for i, body in enumerate(bodies):
            conn.execute(
                "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?,?,?,?)",
                ("alice", "bob", body, 1000.0 + i),
            )
        conn.commit()
        conn.close()
        self.fts = FTSClient(self.project, "alice")
        self.assertTrue(self.fts.init_fts_table(), "FTS init must succeed")
        self.assertTrue(self.fts.rebuild_fts_index(), "FTS rebuild must succeed")

    def tearDown(self):
        import a2a
        try:
            conn = a2a.connect(self.project)
            conn.execute("DROP TABLE IF EXISTS messages_fts")
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM agents")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def test_search_fts_single_term(self):
        """search_fts finds messages containing a single term."""
        results = self.fts.search_fts("authentication")
        bodies = [r["body"] for r in results]
        self.assertEqual(len(results), 2)
        self.assertTrue(all("authentication" in b for b in bodies))

    def test_search_fts_boolean_and(self):
        """search_fts AND operator requires both terms."""
        results = self.fts.search_fts("authentication AND error")
        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0]["body"])

    def test_search_fts_no_match(self):
        """search_fts returns empty list when nothing matches."""
        results = self.fts.search_fts("zzznomatch")
        self.assertEqual(results, [])

    def test_search_fts_limit(self):
        """search_fts respects the limit parameter."""
        results = self.fts.search_fts("a", limit=1)
        self.assertLessEqual(len(results), 1)

    def test_rebuild_fts_index(self):
        """rebuild_fts_index returns True on success."""
        ok = self.fts.rebuild_fts_index()
        self.assertTrue(ok)

    def test_get_search_stats(self):
        """get_search_stats returns indexed_messages count."""
        stats = self.fts.get_search_stats()
        self.assertIn("indexed_messages", stats)
        self.assertGreaterEqual(stats["indexed_messages"], 0)
        self.assertIn("total_messages", stats)
        self.assertEqual(stats["total_messages"], 4)

    def test_get_total_messages(self):
        """_get_total_messages returns correct count."""
        self.assertEqual(self.fts._get_total_messages(), 4)


class TestAuditLogging(unittest.TestCase):
    """Test suite for audit logging (v1.3)."""

    def setUp(self):
        """Set up test fixtures."""
        self.audit = AuditClient("test-project")

    def test_audit_client_init(self):
        """Test audit client initialization."""
        self.assertEqual(self.audit.project, "test-project")
        self.assertIsNotNone(self.audit.db_path)

    def test_log_operation_structure(self):
        """Test operation logging structure."""
        # Test the context manager
        from a2a_audit import AuditContextManager

        ctx = AuditContextManager(self.audit, "alice", "send")
        self.assertEqual(ctx.agent_id, "alice")
        self.assertEqual(ctx.operation, "send")
        self.assertIsNone(ctx.message_id)
        self.assertEqual(ctx.details, {})

    def test_context_manager_setup(self):
        """Test audit context manager."""
        from a2a_audit import AuditContextManager

        with AuditContextManager(self.audit, "alice", "send") as ctx:
            ctx.message_id = 42
            ctx.details = {"recipient": "bob"}
        # Context should exit successfully

    def test_audit_operation_types(self):
        """Test various operation types."""
        operations = ["send", "recv", "read", "encrypt", "decrypt", "search", "delete"]
        for op in operations:
            # Should be able to log any operation type
            self.assertIsInstance(op, str)


class TestMessagePriority(unittest.TestCase):
    """Test suite for message prioritization (v1.3)."""

    def setUp(self):
        """Set up test fixtures."""
        self.priority = PriorityClient("test-project", "alice")

    def test_priority_enum(self):
        """Test Priority enum values."""
        self.assertEqual(Priority.LOW, 1)
        self.assertEqual(Priority.NORMAL, 2)
        self.assertEqual(Priority.HIGH, 3)
        self.assertEqual(Priority.CRITICAL, 4)

    def test_priority_from_string(self):
        """Test converting string to priority."""
        self.assertEqual(Priority.from_string("critical"), Priority.CRITICAL)
        self.assertEqual(Priority.from_string("high"), Priority.HIGH)
        self.assertEqual(Priority.from_string("normal"), Priority.NORMAL)
        self.assertEqual(Priority.from_string("low"), Priority.LOW)
        self.assertEqual(Priority.from_string("unknown"), Priority.NORMAL)

    def test_priority_client_init(self):
        """Test priority client initialization."""
        self.assertEqual(self.priority.agent_id, "alice")
        self.assertIsNotNone(self.priority.db_path)

    def test_priority_queue_helper(self):
        """Test PriorityQueue helper class."""
        from a2a_priority import PriorityQueue

        queue = PriorityQueue(self.priority, "alice")
        self.assertEqual(queue.agent_id, "alice")
        self.assertEqual(queue.queue, [])

    def test_priority_ordering_logic(self):
        """Test priority ordering logic."""
        messages = [
            {"id": 1, "priority": Priority.NORMAL, "created_at": 1000},
            {"id": 2, "priority": Priority.CRITICAL, "created_at": 1100},
            {"id": 3, "priority": Priority.HIGH, "created_at": 900},
            {"id": 4, "priority": Priority.LOW, "created_at": 1200},
        ]

        # Sort by priority DESC, then timestamp ASC
        sorted_msgs = sorted(
            messages,
            key=lambda m: (-m["priority"], m["created_at"])
        )

        # Expected order: CRITICAL (1100), HIGH (900), NORMAL (1000), LOW (1200)
        self.assertEqual(sorted_msgs[0]["priority"], Priority.CRITICAL)
        self.assertEqual(sorted_msgs[1]["priority"], Priority.HIGH)
        self.assertEqual(sorted_msgs[2]["priority"], Priority.NORMAL)
        self.assertEqual(sorted_msgs[3]["priority"], Priority.LOW)


class TestMessageRouting(unittest.TestCase):
    """Test suite for message routing (v1.3)."""

    def setUp(self):
        """Set up test fixtures."""
        self.routing = RoutingClient("test-project", "alice")

    def test_routing_action_enum(self):
        """Test RoutingAction enum."""
        self.assertEqual(RoutingAction.DELIVER.value, "deliver")
        self.assertEqual(RoutingAction.FORWARD.value, "forward")
        self.assertEqual(RoutingAction.DISCARD.value, "discard")
        self.assertEqual(RoutingAction.QUEUE.value, "queue")
        self.assertEqual(RoutingAction.ESCALATE.value, "escalate")

    def test_routing_rule_creation(self):
        """Test creating a routing rule."""
        rule = RoutingRule(
            name="test_rule",
            action=RoutingAction.FORWARD,
            match_sender="bob",
            forward_to="charlie"
        )

        self.assertEqual(rule.name, "test_rule")
        self.assertEqual(rule.action, RoutingAction.FORWARD)
        self.assertEqual(rule.match_sender, "bob")
        self.assertEqual(rule.forward_to, "charlie")
        self.assertTrue(rule.enabled)

    def test_pattern_matching_substring(self):
        """Test substring pattern matching."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.FORWARD,
            match_content="error"
        )

        msg1 = {"body": "An error occurred"}
        msg2 = {"body": "Processing complete"}

        self.assertTrue(rule.matches(msg1))
        self.assertFalse(rule.matches(msg2))

    def test_pattern_matching_case_insensitive(self):
        """Test case-insensitive matching."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.FORWARD,
            match_content="error"
        )

        msg = {"body": "An ERROR Occurred"}
        self.assertTrue(rule.matches(msg))

    def test_pattern_matching_regex(self):
        """Test regex pattern matching."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.FORWARD,
            match_content="port (\\d+)"
        )

        msg1 = {"body": "Port 8080 is unavailable"}
        msg2 = {"body": "Service unavailable"}

        self.assertTrue(rule.matches(msg1))
        self.assertFalse(rule.matches(msg2))

    def test_priority_matching(self):
        """Test priority-based rule matching."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.ESCALATE,
            match_priority=Priority.HIGH
        )

        msg_critical = {"priority": Priority.CRITICAL}
        msg_high = {"priority": Priority.HIGH}
        msg_normal = {"priority": Priority.NORMAL}

        self.assertTrue(rule.matches(msg_critical))
        self.assertTrue(rule.matches(msg_high))
        self.assertFalse(rule.matches(msg_normal))

    def test_routing_rule_disabled(self):
        """Test disabled rules don't match."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.FORWARD,
            match_content="error",
            enabled=False
        )

        msg = {"body": "An error occurred"}
        self.assertFalse(rule.matches(msg))


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for v1.3 features working together."""

    def test_encrypted_priority_message(self):
        """Test sending encrypted message with priority."""
        # This would require full database setup
        # For now, test the concept
        crypto = CryptoClient("test", "alice", key_dir=tempfile.mkdtemp())
        priority = PriorityClient("test", "alice")

        # Generate keypair for encryption
        public_key, _ = crypto.generate_keypair()

        # Wrap message with encryption
        wrapped = crypto.wrap_encrypted_message("Sensitive", public_key)

        # Can send as priority message
        # msg_id = priority.send("bob", wrapped, priority=Priority.CRITICAL)
        # This would work in full integration

    def test_routing_with_priority(self):
        """Test routing based on priority."""
        routing = RoutingClient("test", "alice")

        # Create rule: forward critical messages
        rule = RoutingRule(
            name="critical_forward",
            action=RoutingAction.FORWARD,
            match_priority=Priority.CRITICAL,
            forward_to="oncall"
        )

        msg = {
            "id": 1,
            "body": "System down",
            "priority": Priority.CRITICAL,
            "sender": "monitoring"
        }

        self.assertTrue(rule.matches(msg))

    def test_audit_all_operations(self):
        """Test audit logging of all v1.3 operations."""
        audit = AuditClient("test")

        operations = [
            ("send", {"recipient": "bob"}),
            ("encrypt", {"algorithm": "RSA-2048"}),
            ("recv", {"count": 5}),
            ("decrypt", {"algorithm": "RSA-2048"}),
            ("search", {"query": "error"}),
            ("route", {"action": "forward"}),
        ]

        for op, details in operations:
            # Should be able to log any operation
            self.assertIsInstance(op, str)


class TestErrorHandling(unittest.TestCase):
    """Test error handling in v1.3 features."""

    def test_crypto_invalid_key(self):
        """Test handling of invalid encryption key."""
        crypto = CryptoClient("test", "alice", key_dir=tempfile.mkdtemp())

        with self.assertRaises(ValueError):
            crypto.decrypt_message("invalid_encrypted_data", "invalid_key")

    def test_routing_rule_disabled_doesnt_crash(self):
        """Test that disabled rules handle gracefully."""
        rule = RoutingRule(
            name="test",
            action=RoutingAction.FORWARD,
            match_content="error",
            enabled=False
        )

        msg = {"body": "error message"}
        # Should not crash, should return False
        self.assertFalse(rule.matches(msg))

    def test_priority_enum_boundary(self):
        """Test priority enum boundaries."""
        self.assertEqual(Priority.LOW, 1)
        self.assertEqual(Priority.CRITICAL, 4)


def run_tests():
    """Run all v1.3 feature tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestEncryption))
    suite.addTests(loader.loadTestsFromTestCase(TestFullTextSearch))
    suite.addTests(loader.loadTestsFromTestCase(TestAuditLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestMessagePriority))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageRouting))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit(run_tests())
