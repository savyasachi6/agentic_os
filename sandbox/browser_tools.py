"""
Browser Tools for Agentic OS Sandbox (Lightpanda / Playwright CDP)

Provides browser automation as sandbox tools by connecting to a Lightpanda
(or any CDP-compatible browser) instance via WebSocket.

Connection: reads LIGHTPANDA_CDP_URL (default: ws://127.0.0.1:9222).
Each handler opens a short-lived Playwright session, performs the action,
then disconnects — keeping the Lightpanda server persistent across calls.

Hardware Assumptions:
- Network-bound; no GPU required.
- Runs inside the isolated Sandbox FastAPI worker subprocess.
- Lightpanda must be started *separately* (e.g. `lightpanda serve`);
  this module never spawns or manages the browser process itself.

Available tools (registered in worker.py TOOL_REGISTRY):
    browser-navigate   — goto URL, return title + visible text / HTML
    browser-click      — click a CSS/XPath selector on the current URL
    browser-evaluate   — evaluate a JS expression and return the result
    browser-screenshot — capture a full-page PNG (base64-encoded)
"""

from __future__ import annotations

import base64
import os
import sys
from typing import TYPE_CHECKING

# ── Optional import guard ─────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, Playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(
        "[browser_tools] Warning: playwright is not installed. "
        "Browser tools will be disabled. Install with: pip install playwright",
        file=sys.stderr,
    )

# Import wire models from the lightweight models module (no FastAPI dependency)
from .models import ToolCallRequest, ToolCallResponse  # type: ignore

# ── Helpers ───────────────────────────────────────────────────────────

def _cdp_url() -> str:
    """Return the Lightpanda (or generic CDP) WebSocket endpoint URL."""
    return os.environ.get("LIGHTPANDA_CDP_URL", "ws://127.0.0.1:9222")


def _unavailable() -> ToolCallResponse:
    return ToolCallResponse(
        success=False,
        error=(
            "playwright is not installed in the worker environment. "
            "Install with: pip install playwright && playwright install"
        ),
    )


# ── Tool handlers ─────────────────────────────────────────────────────

def handle_browser_navigate(request: ToolCallRequest) -> ToolCallResponse:
    """
    Navigate to a URL and return the page title plus visible text.

    Request fields:
        path  | args["url"]  — URL to visit (required)
        args["content_type"] — "text" (default) or "html"
        args["timeout_ms"]   — navigation timeout in ms (default 30000)
    """
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    if not url:
        return ToolCallResponse(
            success=False,
            error="Missing 'path' or args['url'] for browser-navigate.",
        )

    content_type: str = request.args.get("content_type", "text")
    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(_cdp_url())
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout_ms)

            title = page.title()
            if content_type == "html":
                content = page.content()            # full HTML
            else:
                content = page.inner_text("body")   # visible text only

            # Cap to 12 000 chars to stay within LLM context budgets
            if len(content) > 12_000:
                content = content[:12_000]
                truncated = True
            else:
                truncated = False

            page.close()
            context.close()
            browser.close()

        return ToolCallResponse(
            success=True,
            result={
                "url": url,
                "title": title,
                "content": content,
                "content_type": content_type,
                "truncated": truncated,
            },
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-navigate failed: {exc}")


def handle_browser_click(request: ToolCallRequest) -> ToolCallResponse:
    """
    Navigate to a URL then click a CSS/XPath selector.

    Request fields:
        path  | args["url"]      — URL to visit (required)
        query | args["selector"] — CSS or XPath selector to click (required)
        args["timeout_ms"]       — action timeout in ms (default 10000)
    """
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    selector = request.query or request.args.get("selector")
    if not url:
        return ToolCallResponse(success=False, error="Missing 'path' or args['url'] for browser-click.")
    if not selector:
        return ToolCallResponse(success=False, error="Missing 'query' or args['selector'] for browser-click.")

    timeout_ms: int = int(request.args.get("timeout_ms", 10_000))

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(_cdp_url())
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout_ms * 3)
            page.locator(selector).click(timeout=timeout_ms)
            result_url = page.url

            page.close()
            context.close()
            browser.close()

        return ToolCallResponse(
            success=True,
            result={"url": url, "selector": selector, "result_url": result_url},
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-click failed: {exc}")


def handle_browser_evaluate(request: ToolCallRequest) -> ToolCallResponse:
    """
    Navigate to a URL and evaluate a JavaScript expression.

    Request fields:
        path  | args["url"]        — URL to visit (required)
        query | args["expression"] — JS expression to evaluate (required)
        args["timeout_ms"]         — navigation timeout in ms (default 30000)
    """
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    expression = request.query or request.args.get("expression")
    if not url:
        return ToolCallResponse(success=False, error="Missing 'path' or args['url'] for browser-evaluate.")
    if not expression:
        return ToolCallResponse(success=False, error="Missing 'query' or args['expression'] for browser-evaluate.")

    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(_cdp_url())
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout_ms)
            result = page.evaluate(expression)

            page.close()
            context.close()
            browser.close()

        return ToolCallResponse(
            success=True,
            result={"url": url, "expression": expression, "value": result},
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-evaluate failed: {exc}")


def handle_browser_screenshot(request: ToolCallRequest) -> ToolCallResponse:
    """
    Navigate to a URL and capture a full-page screenshot (PNG, base64).

    Request fields:
        path | args["url"]   — URL to visit (required)
        args["full_page"]    — bool, default True
        args["timeout_ms"]   — navigation timeout in ms (default 30000)
    """
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    if not url:
        return ToolCallResponse(success=False, error="Missing 'path' or args['url'] for browser-screenshot.")

    full_page: bool = bool(request.args.get("full_page", True))
    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(_cdp_url())
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout_ms)
            png_bytes: bytes = page.screenshot(full_page=full_page)

            page.close()
            context.close()
            browser.close()

        return ToolCallResponse(
            success=True,
            result={
                "url": url,
                "format": "png",
                "encoding": "base64",
                "data": base64.b64encode(png_bytes).decode("ascii"),
            },
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-screenshot failed: {exc}")
