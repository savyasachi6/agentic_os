"""
Unit tests for agent_sandbox/browser_tools.py

All tests use mocked Playwright — no real browser or Chrome instance required.
Run with:  pytest tests/core/test_browser_tools.py -v
"""

from __future__ import annotations

import sys
import os
import unittest
import base64
from unittest.mock import MagicMock, patch, PropertyMock

# ── Path bootstrap ────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global import for the tools being tested
from sandbox import browser_tools as bt
from sandbox.models import ToolCallRequest


def _make_request(**kwargs):
    """Build a ToolCallRequest with sensible defaults."""
    return ToolCallRequest(**kwargs)


# ── Playwright mock factory ────────────────────────────────────────────

def _build_playwright_mock(
    *,
    title: str = "Test Page",
    inner_text: str = "Hello World",
    html: str = "<html><body>Hello World</body></html>",
    evaluate_result=None,
    screenshot_bytes: bytes = b"\x89PNG\r\n",
    result_url: str = "https://example.com/after",
):
    """Return a mock that mimics `sync_playwright().__enter__()` behaviour."""
    mock_page = MagicMock()
    mock_page.title.return_value = title
    mock_page.inner_text.return_value = inner_text
    mock_page.content.return_value = html
    mock_page.evaluate.return_value = evaluate_result
    mock_page.screenshot.return_value = screenshot_bytes
    type(mock_page).url = PropertyMock(return_value=result_url)

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_chromium = MagicMock()
    mock_chromium.connect_over_cdp.return_value = mock_browser

    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium

    # Context-manager protocol: with sync_playwright() as pw
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_pw)
    mock_cm.__exit__ = MagicMock(return_value=False)

    return mock_cm, mock_page


# NOTE: We use create=True in all sync_playwright patches because when playwright
# is not installed the import guard catches ImportError and the name 'sync_playwright'
# is never bound in the module namespace. create=True allows patch() to inject it
# even when it doesn't exist as a module attribute.

class TestBrowserNavigate(unittest.TestCase):

    def test_navigate_success_text(self):
        """Returns page title and visible text on success."""
        cm, _ = _build_playwright_mock(title="Example Domain", inner_text="Example text")
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com")
            resp = bt.handle_browser_navigate(req)

        self.assertTrue(resp.success)
        self.assertEqual(resp.result["title"], "Example Domain")
        self.assertEqual(resp.result["content"], "Example text")
        self.assertEqual(resp.result["content_type"], "text")

    def test_navigate_success_html(self):
        """Returns HTML when content_type='html'."""
        cm, _ = _build_playwright_mock(html="<html><body>hi</body></html>")
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com", args={"content_type": "html"})
            resp = bt.handle_browser_navigate(req)

        self.assertTrue(resp.success)
        self.assertIn("<html>", resp.result["content"])

    def test_navigate_missing_url(self):
        """Missing URL returns success=False with a helpful error."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True):
            req = _make_request()  # no path or args["url"]
            resp = bt.handle_browser_navigate(req)

        self.assertFalse(resp.success)
        self.assertIn("Missing", resp.error)

    def test_navigate_playwright_unavailable(self):
        """Graceful error when playwright is not installed."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", False):
            req = _make_request(path="https://example.com")
            resp = bt.handle_browser_navigate(req)

        self.assertFalse(resp.success)
        self.assertIn("playwright", resp.error.lower())

    def test_navigate_truncates_long_content(self):
        """Content longer than 12000 chars is truncated and flagged."""
        long_text = "x" * 20_000
        cm, _ = _build_playwright_mock(inner_text=long_text)
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com")
            resp = bt.handle_browser_navigate(req)

        self.assertTrue(resp.success)
        self.assertTrue(resp.result["truncated"])
        self.assertEqual(len(resp.result["content"]), 12_000)


class TestBrowserClick(unittest.TestCase):

    def test_click_success(self):
        """Returns success=True with selector and result URL."""
        cm, mock_page = _build_playwright_mock(result_url="https://example.com/clicked")
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com", query="button#submit")
            resp = bt.handle_browser_click(req)

        self.assertTrue(resp.success)
        self.assertEqual(resp.result["selector"], "button#submit")

    def test_click_missing_selector(self):
        """Returns error when selector is not provided."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True):
            req = _make_request(path="https://example.com")  # no query / selector
            resp = bt.handle_browser_click(req)

        self.assertFalse(resp.success)
        self.assertIn("selector", resp.error.lower())

    def test_click_missing_url(self):
        """Returns error when URL is not provided."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True):
            req = _make_request(query="button")  # no path / url
            resp = bt.handle_browser_click(req)

        self.assertFalse(resp.success)


class TestBrowserEvaluate(unittest.TestCase):

    def test_evaluate_success(self):
        """Returns serialised JS result."""
        cm, _ = _build_playwright_mock(evaluate_result=4)
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com", query="2+2")
            resp = bt.handle_browser_evaluate(req)

        self.assertTrue(resp.success)
        self.assertEqual(resp.result["value"], 4)
        self.assertEqual(resp.result["expression"], "2+2")

    def test_evaluate_missing_expression(self):
        """Returns error when no JS expression is provided."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True):
            req = _make_request(path="https://example.com")  # no query / expression
            resp = bt.handle_browser_evaluate(req)

        self.assertFalse(resp.success)


class TestBrowserScreenshot(unittest.TestCase):

    def test_screenshot_success(self):
        """Returns base64-encoded PNG data."""
        png_bytes = b"\x89PNG\r\n\x1aFAKE"
        cm, _ = _build_playwright_mock(screenshot_bytes=png_bytes)
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True), \
             patch.object(bt, "sync_playwright", return_value=cm, create=True):
            req = _make_request(path="https://example.com")
            resp = bt.handle_browser_screenshot(req)

        self.assertTrue(resp.success)
        self.assertEqual(resp.result["format"], "png")
        self.assertEqual(resp.result["encoding"], "base64")
        self.assertEqual(
            base64.b64decode(resp.result["data"]),
            png_bytes,
        )

    def test_screenshot_missing_url(self):
        """Returns error when URL is missing."""
        with patch.object(bt, "PLAYWRIGHT_AVAILABLE", True):
            req = _make_request()
            resp = bt.handle_browser_screenshot(req)

        self.assertFalse(resp.success)


if __name__ == "__main__":
    unittest.main()
