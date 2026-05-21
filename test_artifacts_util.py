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
from _util import strip_html_preamble, make_kit


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
