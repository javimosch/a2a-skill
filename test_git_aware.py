#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for a2a_git_aware.py — git-aware work-collision prevention."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from a2a_git_aware import GitAwareClient, announce_work_status, check_collisions


class TestGitAwareClientBasics(unittest.TestCase):
    """Test GitAwareClient basic functionality."""

    def setUp(self):
        self.client = GitAwareClient("test-agent", ".")

    def test_init_defaults(self):
        """Test default initialization uses current directory."""
        client = GitAwareClient("agent1")
        self.assertEqual(client.agent_id, "agent1")
        self.assertEqual(client.repo_path, Path("."))

    def test_init_custom_path(self):
        """Test initialization with custom repo path."""
        client = GitAwareClient("agent1", "/tmp")
        self.assertEqual(client.repo_path, Path("/tmp"))

    def test_agent_id_stored(self):
        """Test agent_id is stored correctly."""
        self.assertEqual(self.client.agent_id, "test-agent")

    def test_init_empty_agent_id_raises_error(self):
        """GitAwareClient with empty agent_id raises ValueError."""
        with self.assertRaises(ValueError):
            GitAwareClient("")
        with self.assertRaises(ValueError):
            GitAwareClient("   ")

    def test_init_long_agent_id(self):
        """GitAwareClient with very long agent_id does not crash."""
        client = GitAwareClient("a" * 1000)
        self.assertEqual(client.agent_id, "a" * 1000)

    def test_init_repo_path_does_not_exist(self):
        """GitAwareClient with nonexistent repo path still constructs."""
        client = GitAwareClient("agent1", "/nonexistent/path/xyz789")
        self.assertEqual(client.repo_path, Path("/nonexistent/path/xyz789"))
        # Methods should handle gracefully, not crash
        branch = client.get_current_branch()
        self.assertEqual(branch, "unknown")


class TestGitAwareGitCommands(unittest.TestCase):
    """Test git command execution in a real git repository."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary git repo for testing."""
        cls.tmp_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init", cls.tmp_dir], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=cls.tmp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=cls.tmp_dir, capture_output=True
        )
        # Create initial commit
        test_file = Path(cls.tmp_dir) / "README.md"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=cls.tmp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=cls.tmp_dir, capture_output=True
        )
        cls.client = GitAwareClient("tester", cls.tmp_dir)

    def test_get_current_branch_returns_string(self):
        """Test that get_current_branch returns a non-empty string."""
        branch = self.client.get_current_branch()
        self.assertIsInstance(branch, str)
        self.assertGreater(len(branch), 0)

    def test_get_current_branch_not_error(self):
        """Test that get_current_branch doesn't return an error string."""
        branch = self.client.get_current_branch()
        self.assertNotIn("Error", branch)

    def test_get_recent_commits_returns_list(self):
        """Test that get_recent_commits returns a list."""
        commits = self.client.get_recent_commits()
        self.assertIsInstance(commits, list)

    def test_get_recent_commits_not_empty(self):
        """Test that commits list is not empty in our test repo."""
        commits = self.client.get_recent_commits()
        self.assertGreater(len(commits), 0)

    def test_get_recent_commits_structure(self):
        """Test that commit dicts have required keys."""
        commits = self.client.get_recent_commits()
        if commits:
            commit = commits[0]
            self.assertIn("hash", commit)
            self.assertIn("author", commit)
            self.assertIn("message", commit)
            self.assertIn("timestamp", commit)

    def test_get_recent_commits_count_limit(self):
        """Test that count parameter limits results."""
        commits = self.client.get_recent_commits(count=1)
        self.assertLessEqual(len(commits), 1)

    def test_get_recent_commits_large_count_does_not_crash(self):
        """Test that a very large count parameter does not crash."""
        commits = self.client.get_recent_commits(count=99999)
        self.assertIsInstance(commits, list)
        # Should return at most the total number of commits available

    def test_get_recent_commits_zero_count(self):
        """Test that count=0 returns empty list."""
        commits = self.client.get_recent_commits(count=0)
        self.assertEqual(commits, [])

    def test_get_recent_commits_negative_count(self):
        """Test that negative count does not crash and returns empty list."""
        commits = self.client.get_recent_commits(count=-1)
        self.assertIsInstance(commits, list)
        # Should either return empty or handle gracefully

    def test_format_for_bus_in_repo(self):
        """Test format_for_bus returns valid JSON with branch info in a real repo."""
        json_str = self.client.format_for_bus()
        parsed = json.loads(json_str)
        self.assertIn("agent", parsed)
        self.assertIn("branch", parsed)
        self.assertIn("timestamp", parsed)
        self.assertIsInstance(parsed.get("commits"), list)
        self.assertIsInstance(parsed.get("changed_files"), list)

    def test_get_changed_files_returns_list(self):
        """Test that get_changed_files returns a list."""
        files = self.client.get_changed_files()
        self.assertIsInstance(files, list)

    def test_get_changed_files_with_unstaged(self):
        """Test that changed files are detected."""
        # Create an unstaged change
        new_file = Path(self.tmp_dir) / "unstaged.txt"
        new_file.write_text("unstaged content")
        subprocess.run(["git", "add", str(new_file)], cwd=self.tmp_dir, capture_output=True)

        # Modify a tracked file without staging
        readme = Path(self.tmp_dir) / "README.md"
        readme.write_text("modified content")

        files = self.client.get_changed_files()
        self.assertIsInstance(files, list)

        # Reset state
        subprocess.run(["git", "checkout", "--", "README.md"], cwd=self.tmp_dir, capture_output=True)
        subprocess.run(["git", "reset", "HEAD", "unstaged.txt"], cwd=self.tmp_dir, capture_output=True)
        new_file.unlink(missing_ok=True)

    def test_get_changed_files_clean_state(self):
        """Test that get_changed_files returns empty list in clean repo."""
        files = self.client.get_changed_files()
        self.assertIsInstance(files, list)
        # All changes from previous tests should have been cleaned up
        self.assertEqual(files, [])

    def test_get_current_branch_detached_head(self):
        """Test that detached HEAD state returns 'HEAD' not 'unknown'."""
        # Detach HEAD to a specific commit
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=self.tmp_dir
        ).stdout.strip()
        subprocess.run(
            ["git", "checkout", "--detach", commit_hash],
            capture_output=True, cwd=self.tmp_dir
        )
        branch = self.client.get_current_branch()
        # Attach back to main branch
        subprocess.run(
            ["git", "checkout", "-"],
            capture_output=True, cwd=self.tmp_dir
        )
        self.assertEqual(branch, "HEAD",
                         "Detached HEAD should return 'HEAD', not 'unknown'")

    def test_get_changed_files_binary_files(self):
        """Test that binary files in changes don't cause errors."""
        binary_path = Path(self.tmp_dir) / "binary.bin"
        binary_path.write_bytes(bytes(range(256)))
        subprocess.run(["git", "add", "binary.bin"], cwd=self.tmp_dir, capture_output=True)
        files = self.client.get_changed_files()
        # Clean up
        subprocess.run(["git", "reset", "HEAD", "binary.bin"], cwd=self.tmp_dir, capture_output=True)
        binary_path.unlink(missing_ok=True)
        self.assertIsInstance(files, list)


class TestGitAwareGitCommandsFull(unittest.TestCase):
    """Test git command full features in a real git repository."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary git repo for testing."""
        cls.tmp_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init", cls.tmp_dir], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=cls.tmp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=cls.tmp_dir, capture_output=True
        )
        test_file = Path(cls.tmp_dir) / "README.md"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=cls.tmp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=cls.tmp_dir, capture_output=True
        )
        cls.client = GitAwareClient("tester", cls.tmp_dir)

    def test_get_branch_status_structure(self):
        """Test get_branch_status returns complete dict."""
        status = self.client.get_branch_status()
        self.assertIn("branch", status)
        self.assertIn("commits", status)
        self.assertIn("changed_files", status)
        self.assertIn("timestamp", status)
        self.assertIn("agent", status)
        self.assertEqual(status["agent"], "tester")

    def test_get_branch_status_commits_is_list(self):
        """Test get_branch_status returns commits as a list."""
        status = self.client.get_branch_status()
        self.assertIsInstance(status["commits"], list)
        self.assertGreater(len(status["commits"]), 0)

    def test_get_collaboration_summary_returns_string(self):
        """Test that collaboration summary returns a string."""
        summary = self.client.get_collaboration_summary()
        self.assertIsInstance(summary, str)
        self.assertIn("tester", summary)

    def test_get_collaboration_summary_with_changed_files(self):
        """Test collaboration summary shows changed files section."""
        readme = Path(self.tmp_dir) / "README.md"
        original = readme.read_text()
        readme.write_text("modified for summary test")

        summary = self.client.get_collaboration_summary()
        self.assertIn("Changed files:", summary)
        self.assertIn("README.md", summary)

        # Restore
        readme.write_text(original)
        subprocess.run(["git", "checkout", "--", "README.md"],
                       cwd=self.tmp_dir, capture_output=True)

    def test_format_for_bus_returns_valid_json(self):
        """Test that format_for_bus returns valid JSON."""
        json_str = self.client.format_for_bus()
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertIn("branch", parsed)
        self.assertIn("agent", parsed)

    def test_parse_bus_message_valid_json(self):
        """Test parsing valid bus message."""
        data = {"branch": "main", "agent": "alice"}
        message = json.dumps(data)
        result = GitAwareClient.parse_bus_message(message)
        self.assertEqual(result, data)

    def test_parse_bus_message_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        result = GitAwareClient.parse_bus_message("not json {{{")
        self.assertIsNone(result)

    def test_parse_bus_message_plain_text(self):
        """Test parsing plain text returns None."""
        result = GitAwareClient.parse_bus_message("Hello world")
        self.assertIsNone(result)

    def test_parse_bus_message_empty_string(self):
        """Test parsing empty string returns None."""
        result = GitAwareClient.parse_bus_message("")
        self.assertIsNone(result)

    def test_parse_bus_message_partial_json(self):
        """Test parsing partial/incomplete JSON returns None."""
        result = GitAwareClient.parse_bus_message('{"branch": "main", "agent"')
        self.assertIsNone(result)

    def test_parse_bus_message_null_bytes(self):
        """Test parsing JSON with null bytes returns None or handled."""
        result = GitAwareClient.parse_bus_message('{"branch": "main\x00"}')
        # Should not crash; None is acceptable
        self.assertIn(result, (None, {"branch": "main\x00"}))

    def test_parse_bus_message_unicode(self):
        """Test parsing JSON with unicode/emoji content."""
        data = {"branch": "✨-feature", "agent": "Alice 🚀"}
        message = json.dumps(data)
        result = GitAwareClient.parse_bus_message(message)
        self.assertEqual(result, data)

    def test_parse_bus_message_deeply_nested_json(self):
        """Test parsing deeply nested JSON structures."""
        data = {
            "branch": "main",
            "agent": "deep",
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {"key": "value"}
                    }
                }
            },
            "items": [1, [2, [3, [4]]]],
        }
        message = json.dumps(data)
        result = GitAwareClient.parse_bus_message(message)
        self.assertEqual(result, data)

    def test_parse_bus_message_large_json(self):
        """Test parsing a large JSON payload (1MB)."""
        large_list = list(range(10000))
        data = {"branch": "main", "agent": "big", "data": large_list}
        message = json.dumps(data)
        result = GitAwareClient.parse_bus_message(message)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["data"]), 10000)


class TestGitAwareInvalidRepo(unittest.TestCase):
    """Test GitAwareClient behavior outside a git repository."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.client = GitAwareClient("agent1", self.tmp_dir)

    def test_get_current_branch_non_repo(self):
        """Test get_current_branch returns 'unknown' outside git repo."""
        branch = self.client.get_current_branch()
        self.assertEqual(branch, "unknown")

    def test_get_recent_commits_non_repo(self):
        """Test get_recent_commits returns empty list outside git repo."""
        commits = self.client.get_recent_commits()
        self.assertEqual(commits, [])

    def test_get_changed_files_non_repo(self):
        """Test get_changed_files returns empty list outside git repo."""
        files = self.client.get_changed_files()
        self.assertEqual(files, [])

    def test_get_branch_status_non_repo(self):
        """Test get_branch_status returns expected fields outside git repo."""
        status = self.client.get_branch_status()
        self.assertEqual(status["branch"], "unknown")
        self.assertEqual(status["commits"], [])
        self.assertEqual(status["changed_files"], [])
        self.assertIn("timestamp", status)
        self.assertEqual(status["agent"], "agent1")

    def test_format_for_bus_non_repo(self):
        """Test format_for_bus returns valid JSON outside git repo."""
        json_str = self.client.format_for_bus()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["branch"], "unknown")

    def test_get_collaboration_summary_non_repo(self):
        """Test collaboration summary outside git repo returns string with agent info."""
        summary = self.client.get_collaboration_summary()
        self.assertIsInstance(summary, str)
        self.assertIn("agent1", summary)
        # Should mention unknown or no commits
        self.assertTrue("unknown" in summary or "No" in summary or "no commits" in summary)


class TestWorkCollisionDetection(unittest.TestCase):
    """Test detect_work_collision functionality."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init", cls.tmp_dir], capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=cls.tmp_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=cls.tmp_dir, capture_output=True
        )
        test_file = Path(cls.tmp_dir) / "file.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "."], cwd=cls.tmp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=cls.tmp_dir, capture_output=True
        )
        cls.client = GitAwareClient("alice", cls.tmp_dir)

    def test_no_collision_empty_others(self):
        """Test no collision when no other agents reported."""
        result = self.client.detect_work_collision([])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["agent"], "alice")

    def test_collision_structure(self):
        """Test collision result has required keys."""
        result = self.client.detect_work_collision([])
        self.assertIn("agent", result)
        self.assertIn("branch", result)
        self.assertIn("warnings", result)
        self.assertIn("recommendations", result)

    def test_same_branch_collision(self):
        """Test collision detected when same branch."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": my_branch,
            "changed_files": [],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        self.assertGreater(len(result["warnings"]), 0)
        self.assertTrue(any("bob" in w for w in result["warnings"]))

    def test_file_overlap_collision(self):
        """Test collision detected when files overlap."""
        # Create a changed file to detect overlap
        overlap_file = Path(self.tmp_dir) / "overlap.txt"
        overlap_file.write_text("changed")

        other_status = {
            "agent": "bob",
            "branch": "feature-branch",  # different branch
            "changed_files": ["overlap.txt"],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # No file overlap in changed files (diff --name-only shows staged/unstaged)
        self.assertIsInstance(result["warnings"], list)

        # Clean up
        overlap_file.unlink(missing_ok=True)

    def test_file_overlap_actual_detection(self):
        """Test overlapping file changes produce a warning."""
        # Modify a tracked file (git diff --name-only shows this)
        tracked_file = Path(self.tmp_dir) / "file.txt"
        original = tracked_file.read_text()
        tracked_file.write_text("overlap content for tracked file")

        other_status = {
            "agent": "bob",
            "branch": "different-branch",
            "changed_files": ["file.txt"],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])

        # Should have at least one warning about overlapping files
        overlap_warnings = [w for w in result["warnings"] if "file.txt" in w]
        self.assertGreater(len(overlap_warnings), 0,
                          "Expected a warning about overlapping file changes")

        # Restore
        tracked_file.write_text(original)
        subprocess.run(["git", "checkout", "--", "file.txt"],
                       cwd=self.tmp_dir, capture_output=True)

    def test_no_collision_different_branch_files(self):
        """Test no collision when different branches and no file overlap."""
        other_status = {
            "agent": "bob",
            "branch": "feature-bob",
            "changed_files": ["bob_only_file.py"],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Warnings list exists and is a list (may or may not have content)
        self.assertIsInstance(result["warnings"], list)

    def test_multiple_agents(self):
        """Test collision check with multiple agents."""
        my_branch = self.client.get_current_branch()
        others = [
            {"agent": "bob", "branch": my_branch, "changed_files": [], "commits": []},
            {"agent": "carol", "branch": "other", "changed_files": [], "commits": []},
        ]
        result = self.client.detect_work_collision(others)
        # At least one collision with bob (same branch)
        self.assertGreater(len(result["warnings"]), 0)

    def test_duplicate_commit_collision(self):
        """Test duplicate commit hash detection creates a warning."""
        my_commits = self.client.get_recent_commits(count=1)
        if not my_commits:
            self.skipTest("No commits to test duplicate detection")
        commit_hash = my_commits[0]["hash"]

        other_status = {
            "agent": "bob",
            "branch": "other-branch",
            "changed_files": [],
            "commits": [{"hash": commit_hash, "message": "same commit"}],
        }
        result = self.client.detect_work_collision([other_status])

        # Should have a warning about duplicate commits
        duplicate_warnings = [w for w in result["warnings"] if "Duplicate" in w or "duplicate" in w]
        self.assertGreater(len(duplicate_warnings), 0,
                          "Expected a warning about duplicate commits")

    def test_branch_stored_in_result(self):
        """Test that the result includes the current branch."""
        result = self.client.detect_work_collision([])
        my_branch = self.client.get_current_branch()
        self.assertEqual(result["branch"], my_branch)

    def test_collision_missing_branch_key(self):
        """Collision detection handles other status with missing branch key."""
        other_status = {
            "agent": "bob",
            # no "branch" key
            "changed_files": [],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Should not crash; warnings may or may not include bob
        self.assertIsInstance(result["warnings"], list)

    def test_collision_missing_changed_files_key(self):
        """Collision detection handles other status with missing changed_files key."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": my_branch,
            # no "changed_files" key
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Should not crash; at least same-branch warning
        self.assertGreater(len(result["warnings"]), 0)

    def test_collision_empty_agent_id(self):
        """Collision detection handles other status with empty agent_id."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "",
            "branch": my_branch,
            "changed_files": [],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Should not crash
        self.assertIsInstance(result["warnings"], list)

    def test_collision_none_commits_key(self):
        """Collision detection handles other status with None instead of commits list."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": "different-branch",
            "changed_files": [],
            # 'commits' key missing entirely
        }
        result = self.client.detect_work_collision([other_status])
        # Should not crash and produce no collisions
        self.assertIsInstance(result["warnings"], list)

    def test_collision_self_comparison(self):
        """Comparing against own status doesn't create false warnings."""
        my_branch = self.client.get_current_branch()
        my_files = self.client.get_changed_files()
        my_commits = self.client.get_recent_commits(count=3)
        own_status = {
            "agent": "alice",
            "branch": my_branch,
            "changed_files": my_files,
            "commits": [{"hash": c["hash"]} for c in my_commits],
        }
        result = self.client.detect_work_collision([own_status])
        # Should detect same-branch collision (it's the same info but from 'another' agent)
        self.assertGreater(len(result["warnings"]), 0)

    def test_collision_none_changed_files_does_not_crash(self):
        """detect_work_collision handles None changed_files without crashing."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": my_branch,
            "changed_files": None,
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Should NOT crash; same-branch warning is expected, file overlap should be skipped
        self.assertIsInstance(result["warnings"], list)
        self.assertGreater(len(result["warnings"]), 0)

    def test_collision_commits_none_does_not_crash(self):
        """detect_work_collision handles None commits without crashing."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": "different-branch",
            "changed_files": [],
            "commits": None,
        }
        result = self.client.detect_work_collision([other_status])
        # Should NOT crash; no collisions expected
        self.assertIsInstance(result["warnings"], list)

    def test_collision_many_agents_does_not_degrade(self):
        """detect_work_collision handles many agents with no issues."""
        my_branch = self.client.get_current_branch()
        others = []
        for i in range(50):
            others.append({
                "agent": f"agent-{i}",
                "branch": f"branch-{i}" if i % 2 == 0 else my_branch,
                "changed_files": [],
                "commits": [],
            })
        result = self.client.detect_work_collision(others)
        # Should produce warnings for agents on the same branch
        self.assertGreaterEqual(len(result["warnings"]), 25)

    def test_collision_empty_branch_other_agent(self):
        """detect_work_collision handles empty branch name in other status."""
        my_branch = self.client.get_current_branch()
        other_status = {
            "agent": "bob",
            "branch": "",
            "changed_files": [],
            "commits": [],
        }
        result = self.client.detect_work_collision([other_status])
        # Should not crash; comparison '' == my_branch likely false
        self.assertIsInstance(result["warnings"], list)


class TestHelperFunctions(unittest.TestCase):
    """Test module-level helper functions."""

    def test_announce_work_status(self):
        """Test announce_work_status calls send and prints."""
        mock_a2a = MagicMock()
        client = GitAwareClient("alice", ".")

        with patch("builtins.print") as mock_print:
            announce_work_status(client, mock_a2a)

        mock_a2a.send.assert_called_once()
        call_args = mock_a2a.send.call_args
        self.assertEqual(call_args[0][0], "all")
        body = call_args[0][1]
        parsed = json.loads(body)
        self.assertIn("agent", parsed)

    def test_announce_work_status_empty_agent_id(self):
        """Test announce_work_status with empty agent_id raises ValueError."""
        with self.assertRaises(ValueError):
            GitAwareClient("", ".")

    def test_check_collisions_no_agents(self):
        """Test check_collisions with empty agent list."""
        mock_client = MagicMock()
        mock_client.detect_work_collision.return_value = {
            "warnings": [], "recommendations": [], "agent": "alice"
        }
        mock_a2a = MagicMock()

        with patch("builtins.print") as mock_print:
            check_collisions(mock_client, mock_a2a, [])

        mock_client.detect_work_collision.assert_called_once()

    def test_check_collisions_with_warnings(self):
        """Test check_collisions prints warnings when found."""
        mock_client = MagicMock()
        mock_client.detect_work_collision.return_value = {
            "warnings": ["⚠️  bob also working on 'main'"],
            "recommendations": ["Coordinate with bob"],
            "agent": "alice"
        }
        mock_a2a = MagicMock()

        with patch("builtins.print") as mock_print:
            check_collisions(mock_client, mock_a2a, ["bob"])

        # Should print warnings
        printed = [str(c) for c in mock_print.call_args_list]
        self.assertTrue(any("bob" in p for p in printed))

    def test_check_collisions_no_warnings_message(self):
        """Test check_collisions prints success message when no warnings."""
        mock_client = MagicMock()
        mock_client.detect_work_collision.return_value = {
            "warnings": [], "recommendations": [], "agent": "alice"
        }
        mock_a2a = MagicMock()

        with patch("builtins.print") as mock_print:
            check_collisions(mock_client, mock_a2a, ["bob"])

        printed = [str(c) for c in mock_print.call_args_list]
        self.assertTrue(any("No" in p or "no" in p for p in printed),
                       "Expected 'No work collisions detected' message when no warnings")

    def test_check_collisions_none_agents(self):
        """Test check_collisions handles None instead of agent list."""
        mock_client = MagicMock()
        mock_client.detect_work_collision.return_value = {
            "warnings": [], "recommendations": [], "agent": "alice"
        }
        mock_a2a = MagicMock()

        with patch("builtins.print") as mock_print:
            check_collisions(mock_client, mock_a2a, None)

        # Should still call detect_work_collision and print a message
        mock_client.detect_work_collision.assert_called_once()
        printed = [str(c) for c in mock_print.call_args_list]
        self.assertTrue(any("No" in p or "no" in p for p in printed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
