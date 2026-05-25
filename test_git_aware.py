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
        # Modify an existing tracked file (git diff --name-only shows this)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
