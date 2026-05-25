#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for examples/artifacts/_util.py shared utilities."""

import sys
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add artifacts dir to path
sys.path.insert(0, str(Path(__file__).parent / "examples" / "artifacts"))
from _util import (
    strip_html_preamble, strip_code_fence, extract_first_code_block,
    make_kit, send_task, run_a2a, run_a2a_json, ascii_chart, compute_analysis,
    find_a2a, find_spawn, wait_for_messages, SpawnManager,
)


class TestStripHtmlPreamble(unittest.TestCase):
    """Test the strip_html_preamble() helper."""

    def test_strips_text_before_doctype(self):
        """Text before <!DOCTYPE is stripped."""
        result = strip_html_preamble("prefix text <!DOCTYPE html><html></html>")
        self.assertEqual(result, "<!DOCTYPE html><html></html>")

    def test_strips_text_before_html_tag(self):
        """Text before <html tag is stripped when no DOCTYPE."""
        result = strip_html_preamble("leading text <html><body>hello</body></html>")
        self.assertEqual(result, "<html><body>hello</body></html>")

    def test_returns_unchanged_when_no_preamble(self):
        """Already clean HTML with DOCTYPE is returned as-is."""
        payload = "<!DOCTYPE html><html><head></head><body></body></html>"
        result = strip_html_preamble(payload)
        self.assertEqual(result, payload)

    def test_returns_unchanged_when_only_html_tag(self):
        """HTML starting directly with <html is returned as-is."""
        payload = "<html><body>content</body></html>"
        result = strip_html_preamble(payload)
        self.assertEqual(result, payload)

    def test_handles_lowercase_doctype(self):
        """<!doctype html in lowercase is found correctly."""
        result = strip_html_preamble("intro <!doctype html><html></html>")
        self.assertEqual(result, "<!doctype html><html></html>")

    def test_handles_no_html_at_all(self):
        """Plain text with no HTML content is returned unchanged."""
        payload = "just some random text without any HTML markers"
        result = strip_html_preamble(payload)
        self.assertEqual(result, payload)

    def test_handles_empty_string(self):
        """Empty string is returned unchanged."""
        result = strip_html_preamble("")
        self.assertEqual(result, "")

    def test_strips_multiline_preamble(self):
        """Multi-line preamble before DOCTYPE is stripped."""
        payload = "Here is my HTML page:\nIt looks great.\n<!DOCTYPE html>\n<html>\n</html>"
        result = strip_html_preamble(payload)
        self.assertEqual(result, "<!DOCTYPE html>\n<html>\n</html>")

    def test_doctype_without_html_tag(self):
        """DOMParser-style short DOCTYPE without <html is handled."""
        payload = "text <!DOCTYPE html>\ncontent"
        result = strip_html_preamble(payload)
        self.assertEqual(result, "<!DOCTYPE html>\ncontent")


class TestStripCodeFence(unittest.TestCase):
    """Test the strip_code_fence() helper."""

    def test_strips_triple_backtick_fence(self):
        """Triple-backtick fence with language tag is stripped."""
        result = strip_code_fence("```html\n<!DOCTYPE html>\n<html></html>\n```")
        self.assertEqual(result, "<!DOCTYPE html>\n<html></html>")

    def test_strips_triple_tilde_fence(self):
        """Triple-tilde fence is stripped."""
        result = strip_code_fence("~~~\ncontent here\n~~~")
        self.assertEqual(result, "content here")

    def test_strips_fence_with_no_language(self):
        """Fence without language tag is stripped."""
        result = strip_code_fence("```\nraw content\n```")
        self.assertEqual(result, "raw content")

    def test_returns_unchanged_no_fence(self):
        """No fence marker returns body unchanged."""
        payload = "just plain text"
        result = strip_code_fence(payload)
        self.assertEqual(result, payload)

    def test_handles_empty_string(self):
        """Empty string is returned unchanged."""
        result = strip_code_fence("")
        self.assertEqual(result, "")

    def test_unmatched_fence_returns_unchanged(self):
        """Opening fence without matching close returns body unchanged."""
        payload = "```python\nprint('hello')"
        result = strip_code_fence(payload)
        self.assertEqual(result, payload)

    def test_strips_trailing_blank_lines(self):
        """Trailing blank lines inside the fence are stripped."""
        result = strip_code_fence("```yaml\nkey: value\n\n\n```")
        self.assertEqual(result, "key: value")

    def test_multiple_fences_only_strips_outermost(self):
        """Only the outermost fence is stripped; inner fences preserved."""
        payload = "```\nouter\n```\n```\ninner\n```\n"
        # The outer fence is stripped, closing at first ```
        result = strip_code_fence(payload.strip())
        self.assertIn("outer", result)


class TestExtractFirstCodeBlock(unittest.TestCase):
    """Test the extract_first_code_block() helper."""

    def test_extracts_code_block_from_preamble(self):
        """Preamble before a code fence is stripped."""
        result = extract_first_code_block("Here is my code:\n```python\nx = 1\n```")
        self.assertEqual(result, "x = 1")

    def test_returns_plain_text_when_no_fence(self):
        """Plain text without fence is returned as-is."""
        payload = "no fence here"
        result = extract_first_code_block(payload)
        self.assertEqual(result, payload)

    def test_extracts_first_of_multiple_blocks(self):
        """Only the first code block is extracted."""
        result = extract_first_code_block("```\nfirst\n```\n```\nsecond\n```")
        self.assertEqual(result, "first")

    def test_handles_tilde_fence(self):
        """Tilde fence is handled correctly."""
        result = extract_first_code_block("~~~svg\n<svg></svg>\n~~~")
        self.assertEqual(result, "<svg></svg>")

    def test_handles_empty_string(self):
        """Empty string is returned unchanged."""
        result = extract_first_code_block("")
        self.assertEqual(result, "")

    def test_strips_nested_fence_content(self):
        """Content inside a fence with nested backticks is extracted."""
        result = extract_first_code_block("```\ncode inside\n```\nafter")
        self.assertEqual(result, "code inside")

    def test_fence_without_close_returns_as_is(self):
        """Unclosed fence with no close marker returns as-is."""
        payload = "```yaml\nkey: value"
        result = extract_first_code_block(payload)
        self.assertEqual(result, payload)


class TestMakeKit(unittest.TestCase):
    """Test the make_kit() kit prompt builder."""

    def test_kit_contains_agent_id(self):
        """Kit prompt includes the agent's identity."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("test-agent", kit)

    def test_kit_contains_project(self):
        """Kit prompt includes the project name."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("myproject", kit)

    def test_kit_contains_instructions(self):
        """Kit prompt includes the role instructions."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("do the thing", kit)

    def test_kit_has_hard_cap(self):
        """Kit prompt includes the hard iteration cap."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("8 loop iterations", kit)

    def test_kit_has_empty_recv_rule(self):
        """Kit prompt includes the 3-empty-recv rule."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("3 times in a row", kit)

    def test_kit_has_no_write_disk_rule(self):
        """Kit prompt includes the no-write-to-disk ground rule."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("Do NOT write any files to disk", kit)

    def test_kit_has_recv_example(self):
        """Kit prompt includes the recv command example."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("$A2A recv --as", kit)

    def test_kit_has_send_example(self):
        """Kit prompt includes the send command example."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("$A2A send", kit)

    def test_kit_has_status_done(self):
        """Kit prompt includes the status done example."""
        kit = make_kit("test-agent", "tester", "do the thing", "myproject")
        self.assertIn("status done", kit)


class TestMakeKitEdgeCases(unittest.TestCase):
    """Edge cases for make_kit()."""

    def test_kit_with_empty_agent_id(self):
        """make_kit with empty agent_id still produces output."""
        kit = make_kit("", "tester", "do the thing", "myproject")
        self.assertIsInstance(kit, str)
        self.assertIn("tester", kit)

    def test_kit_with_empty_role(self):
        """make_kit with empty role still produces output."""
        kit = make_kit("test-agent", "", "do the thing", "myproject")
        self.assertIsInstance(kit, str)
        self.assertIn("test-agent", kit)

    def test_kit_with_empty_instructions(self):
        """make_kit with empty instructions still produces output."""
        kit = make_kit("test-agent", "tester", "", "myproject")
        self.assertIsInstance(kit, str)
        self.assertIn("Ground rules", kit)

    def test_kit_with_empty_project(self):
        """make_kit with empty project still produces output."""
        kit = make_kit("test-agent", "tester", "do the thing", "")
        self.assertIsInstance(kit, str)
        self.assertIn("A2A_PROJECT=", kit)


class TestRunA2A(unittest.TestCase):
    """Test the run_a2a() helper."""

    def test_run_a2a_fails_with_missing_bin(self):
        """run_a2a returns empty string when binary doesn't exist."""
        result = run_a2a("list --json", "/nonexistent/a2a", "test-proj")
        self.assertEqual(result, "")

    def test_run_a2a_timeout_on_hung_command(self):
        """run_a2a times out when the command does not complete."""
        result = run_a2a("list --json", "/bin/sleep", "test-proj", timeout=1)
        self.assertEqual(result, "")


class TestSendTask(unittest.TestCase):
    """Test the send_task() helper."""

    def test_send_task_exists_and_callable(self):
        """send_task is a callable function with the expected signature."""
        self.assertTrue(callable(send_task))
        import inspect
        sig = inspect.signature(send_task)
        params = list(sig.parameters.keys())
        self.assertIn("a2a_bin", params)
        self.assertIn("agent_id", params)
        self.assertIn("body", params)
        self.assertIn("project", params)

    def test_send_task_fails_with_missing_bin(self):
        """send_task returns False when a2a binary doesn't exist."""
        result = send_task("/nonexistent/a2a", "test-proj", "test-agent", "hello world")
        self.assertFalse(result)


class TestAsciiChart(unittest.TestCase):
    """Test the ascii_chart() helper."""

    def test_returns_string(self):
        """ascii_chart returns a string."""
        result = ascii_chart([1, 2, 3], width=10, height=5, title="Test")
        self.assertIsInstance(result, str)

    def test_contains_title(self):
        """Chart output includes the title."""
        result = ascii_chart([1, 2, 3], width=10, height=5, title="MyChart")
        self.assertIn("MyChart", result)

    def test_contains_min_max(self):
        """Chart includes min and max values."""
        result = ascii_chart([10, 20, 30, 25], width=10, height=5, title="Test")
        self.assertIn("10.0", result)
        self.assertIn("30.0", result)

    def test_contains_statistics(self):
        """Chart includes Statistics section."""
        result = ascii_chart([5, 10, 15], width=10, height=5, title="Test")
        self.assertIn("Statistics", result)

    def test_contains_trend(self):
        """Chart includes trend direction."""
        result = ascii_chart([1, 2, 3, 4, 5], width=10, height=5, title="Test")
        self.assertIn("Trend", result)
        self.assertIn("Increasing", result)

    def test_detects_decreasing_trend(self):
        """Decreasing data shows Decreasing trend."""
        result = ascii_chart([100, 90, 80, 70], width=10, height=5, title="Test")
        # Allow either unicode emoji or ascii representation
        self.assertTrue("Decreasing" in result or "decreasing" in result.lower())

    def test_empty_data(self):
        """Empty list returns placeholder."""
        result = ascii_chart([], width=10, height=5, title="Test")
        self.assertEqual(result, "[empty data]")

    def test_contains_y_axis_labels(self):
        """Chart includes Y-axis labels with pipeline separator."""
        result = ascii_chart([10, 20, 30], width=10, height=5, title="Test")
        self.assertIn("|", result)

    def test_single_value(self):
        """Single value chart still produces output."""
        result = ascii_chart([42], width=10, height=5, title="Single")
        self.assertIn("Single", result)
        self.assertIn("42", result)

    def test_all_same_values(self):
        """All same values produces a stable flat chart."""
        result = ascii_chart([5, 5, 5, 5, 5], width=10, height=5, title="Flat")
        self.assertIn("Flat", result)
        self.assertIn("Statistics", result)

    def test_negative_values(self):
        """Negative values are handled correctly."""
        result = ascii_chart([-10, -5, 0, -3, -8], width=10, height=5, title="Negative")
        self.assertIn("Negative", result)
        self.assertIn("-10", result)
        self.assertIn("-5", result)

    def test_two_element_chart(self):
        """Two-element chart still renders correctly."""
        result = ascii_chart([100, 200], width=5, height=3, title="Two")
        self.assertIn("Two", result)
        self.assertIn("100", result)
        self.assertIn("200", result)


class TestComputeAnalysis(unittest.TestCase):
    """Test the compute_analysis() helper."""

    def test_returns_dict(self):
        """compute_analysis returns a dict."""
        result = compute_analysis([1, 2, 3])
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """Result has all expected keys."""
        result = compute_analysis([5, 10, 15])
        expected_keys = {"n", "min", "max", "mean", "median", "std_dev", "range", "trend", "volatility"}
        self.assertTrue(expected_keys.issubset(result.keys()))

    def test_basic_stats(self):
        """Mean, min, max, median are correct."""
        result = compute_analysis([2, 4, 6, 8])
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["min"], 2)
        self.assertEqual(result["max"], 8)
        self.assertEqual(result["mean"], 5)
        self.assertEqual(result["median"], 5)

    def test_empty_data(self):
        """Empty list returns empty dict."""
        result = compute_analysis([])
        self.assertEqual(result, {})

    def test_single_value(self):
        """Single value has basic stats."""
        result = compute_analysis([42])
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["min"], 42)
        self.assertEqual(result["max"], 42)

    def test_increasing_trend(self):
        """Upward trend is detected."""
        result = compute_analysis([10, 20, 30, 40, 50])
        self.assertEqual(result["trend"], "increasing")

    def test_decreasing_trend(self):
        """Downward trend is detected."""
        result = compute_analysis([50, 40, 30, 20, 10])
        self.assertEqual(result["trend"], "decreasing")

    def test_std_dev_nonzero(self):
        """Standard deviation is positive for varied data."""
        result = compute_analysis([10, 20, 30, 40, 50])
        self.assertGreater(result["std_dev"], 0)

    def test_range_positive(self):
        """Range is positive for min < max."""
        result = compute_analysis([5, 10, 15])
        self.assertEqual(result["range"], 10)

    def test_volatility_nonzero(self):
        """Volatility is positive for varying data."""
        result = compute_analysis([10, 20, 10, 30, 10])
        self.assertGreater(result["volatility"], 0)

    def test_all_same_values(self):
        """All same values have zero range, zero std_dev, stable trend."""
        result = compute_analysis([5, 5, 5, 5])
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["range"], 0)
        self.assertEqual(result["std_dev"], 0)
        self.assertEqual(result["trend"], "stable")

    def test_negative_values_stats(self):
        """Negative values produce correct mean and median."""
        result = compute_analysis([-10, -5, 0, -3, -8])
        self.assertEqual(result["min"], -10)
        self.assertEqual(result["max"], 0)

    def test_stable_trend_detected(self):
        """Identical values produce stable trend."""
        result = compute_analysis([5, 5, 5, 5])
        self.assertEqual(result["trend"], "stable")

    def test_two_element_analysis(self):
        """Two elements produce valid stats."""
        result = compute_analysis([10, 20])
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["min"], 10)
        self.assertEqual(result["max"], 20)
        self.assertEqual(result["median"], 15)


class TestFindA2A(unittest.TestCase):
    """Test the find_a2a() binary locator."""

    @patch("_util.os.path.isfile")
    @patch("_util.os.access")
    def test_find_via_candidate_path(self, mock_access, mock_isfile):
        """find_a2a returns path when a candidate file exists and is executable."""
        mock_isfile.return_value = True
        mock_access.return_value = True
        result = find_a2a("/some/script/dir")
        # Should find via the first candidate: ../../../a2a relative to script_dir
        self.assertIsNotNone(result)

    @patch("_util.os.path.isfile")
    @patch("_util.os.access")
    def test_find_returns_none_when_no_candidates(self, mock_access, mock_isfile):
        """find_a2a returns None when no candidate path exists and command -v fails."""
        mock_isfile.return_value = False
        mock_access.return_value = False
        with patch("_util.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = find_a2a("/nonexistent/script/dir")
        self.assertIsNone(result)


class TestFindSpawn(unittest.TestCase):
    """Test the find_spawn() binary locator."""

    @patch("_util.find_a2a")
    @patch("_util.os.path.isfile")
    @patch("_util.os.access")
    def test_find_spawn_next_to_a2a(self, mock_access, mock_isfile, mock_find_a2a):
        """find_spawn returns path when a2a-spawn is next to a2a binary."""
        mock_find_a2a.return_value = "/usr/local/bin/a2a"
        mock_isfile.return_value = True
        mock_access.return_value = True
        result = find_spawn("/some/script/dir")
        self.assertEqual(result, "/usr/local/bin/a2a-spawn")

    @patch("_util.find_a2a")
    @patch("_util.os.path.isfile")
    @patch("_util.os.access")
    def test_find_spawn_returns_none(self, mock_access, mock_isfile, mock_find_a2a):
        """find_spawn returns None when no candidate exists."""
        mock_find_a2a.return_value = None
        mock_isfile.return_value = False
        mock_access.return_value = False
        with patch("_util.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            result = find_spawn("/nonexistent/script/dir")
        self.assertIsNone(result)


class TestRunA2AJson(unittest.TestCase):
    """Test the run_a2a_json() helper."""

    @patch("_util.run_a2a")
    def test_parses_valid_json(self, mock_run_a2a):
        """run_a2a_json parses valid JSON output."""
        mock_run_a2a.return_value = '[{"id": "alice", "status": "active"}]'
        result = run_a2a_json("list", "/bin/a2a", "test-proj")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "alice")

    @patch("_util.run_a2a")
    def test_returns_empty_on_empty_output(self, mock_run_a2a):
        """run_a2a_json returns [] when run_a2a returns empty string."""
        mock_run_a2a.return_value = ""
        result = run_a2a_json("list", "/bin/a2a", "test-proj")
        self.assertEqual(result, [])

    @patch("_util.run_a2a")
    def test_returns_empty_on_invalid_json(self, mock_run_a2a):
        """run_a2a_json returns [] when output is not valid JSON."""
        mock_run_a2a.return_value = "not valid json {{{"
        result = run_a2a_json("list", "/bin/a2a", "test-proj")
        self.assertEqual(result, [])


class TestSpawnManager(unittest.TestCase):
    """Test the SpawnManager lifecycle."""

    def test_add_stores_pid(self):
        """add() stores a PID in the manager's list."""
        mgr = SpawnManager()
        mgr.add(12345)
        self.assertIn(12345, mgr.pids)

    def test_add_multiple_pids(self):
        """add() stores multiple PIDs."""
        mgr = SpawnManager()
        mgr.add(100)
        mgr.add(200)
        mgr.add(300)
        self.assertEqual(len(mgr.pids), 3)

    def test_cleanup_kills_all_pids(self):
        """cleanup() sends SIGTERM to all stored PIDs."""
        mgr = SpawnManager()
        mgr.add(99999)
        mgr.add(88888)
        with patch("_util.os.kill") as mock_kill:
            mgr.cleanup()
        self.assertEqual(mock_kill.call_count, 2)
        mock_kill.assert_any_call(99999, 15)  # SIGTERM = 15
        mock_kill.assert_any_call(88888, 15)

    def test_cleanup_does_not_raise_on_missing_pid(self):
        """cleanup() handles ProcessLookupError gracefully."""
        mgr = SpawnManager()
        mgr.add(99999)
        with patch("_util.os.kill", side_effect=ProcessLookupError):
            mgr.cleanup()


class TestWaitForMessages(unittest.TestCase):
    """Test the wait_for_messages() helper."""

    @patch("_util.run_a2a_json")
    def test_returns_early_when_all_senders_heard(self, mock_run_a2a_json):
        """Returns as soon as all expected senders have been heard."""
        mock_run_a2a_json.return_value = [
            {"sender": "alice", "body": "hello"},
            {"sender": "bob", "body": "world"},
        ]
        with patch("time.time", return_value=100):
            result = wait_for_messages("/bin/a2a", "proj", "recvr", {"alice", "bob"}, timeout=10)
        self.assertIn("alice", result)
        self.assertIn("bob", result)
        self.assertEqual(result["alice"], "hello")
        self.assertEqual(result["bob"], "world")

    @patch("_util.run_a2a_json")
    def test_ignores_unknown_senders(self, mock_run_a2a_json):
        """Messages from senders not in expected set are ignored."""
        mock_run_a2a_json.return_value = [
            {"sender": "unknown", "body": "ignored"},
        ]
        with patch("time.time", side_effect=[100, 101, 106]):
            result = wait_for_messages("/bin/a2a", "proj", "recvr", {"alice"}, timeout=5)
        self.assertNotIn("unknown", result)


class TestExtractFirstCodeBlockEdgeCases(unittest.TestCase):
    """Additional edge cases for extract_first_code_block()."""

    def test_multiline_preamble_before_fence(self):
        """Multi-line preamble before a code fence is stripped."""
        result = extract_first_code_block("Here is my solution:\n\nI think the answer is:\n\n```python\nx = 42\nprint(x)\n```")
        self.assertEqual(result, "x = 42\nprint(x)")

    def test_unmatched_opening_fence_returns_as_is(self):
        """Opening fence with no closing marker returns the whole body."""
        payload = "```python\nx = 1\ny = 2"
        result = extract_first_code_block(payload)
        self.assertEqual(result, payload)

    def test_content_with_both_fence_types(self):
        """Content with ~~~ fence only is extracted correctly."""
        payload = "~~~\nouter\n~~~"
        result = extract_first_code_block(payload)
        self.assertEqual(result, "outer")

    def test_fence_with_single_tick_preserved(self):
        """Single backtick code spans are not treated as fences."""
        payload = "Use `a2a list --json` to see peers."
        result = extract_first_code_block(payload)
        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()
