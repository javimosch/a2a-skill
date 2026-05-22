#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for examples/artifacts/_util.py shared utilities."""

import sys
import json
import unittest
import tempfile
from pathlib import Path

# Add artifacts dir to path
sys.path.insert(0, str(Path(__file__).parent / "examples" / "artifacts"))
from _util import strip_html_preamble, strip_code_fence, extract_first_code_block, make_kit


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


if __name__ == "__main__":
    unittest.main()
