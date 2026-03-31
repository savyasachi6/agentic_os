"""
Browser Tools for Agentic OS Sandbox (Playwright / Generic CDP) - Async Version (Phase 98)

Provides browser automation as sandbox tools by connecting to a 
CDP-compatible browser instance via WebSocket.

Connection: reads BROWSER_WS_URL (default: ws://127.0.0.1:9222).
Each handler opens a short-lived Playwright session, performs the action,
then disconnects — keeping the browser server persistent across calls.
"""

from __future__ import annotations

import base64
import os
import sys
from typing import TYPE_CHECKING

# ── Optional import guard ─────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright, Playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(
        "[browser_tools] Warning: playwright (async) is not installed. "
        "Browser tools will be disabled.",
        file=sys.stderr,
    )

# Import wire models
from .models import ToolCallRequest, ToolCallResponse  # type: ignore

# ── Helpers ───────────────────────────────────────────────────────────

def _cdp_url() -> str:
    """Return the Generic CDP WebSocket endpoint URL."""
    return os.environ.get("BROWSER_WS_URL", "ws://127.0.0.1:9222")


def _unavailable() -> ToolCallResponse:
    return ToolCallResponse(
        success=False,
        error=(
            "playwright (async) is not installed in the worker environment. "
        ),
    )


async def _extract_search_results(page) -> str:
    """Extract organic results from Google/DDG to reduce noise for the LLM."""
    try:
        # Google-specific organic result extraction
        results = []
        #有機結果常見類 
        items = await page.query_selector_all("div.g")
        for item in items[:6]:
            title_el = await item.query_selector("h3")
            link_el = await item.query_selector("a")
            snippet_el = await item.query_selector("div.VwiC3b")
            
            if title_el and link_el:
                title = await title_el.inner_text()
                url = await link_el.get_attribute("href")
                snippet = await snippet_el.inner_text() if snippet_el else ""
                results.append(f"### {title}\nURL: {url}\n{snippet}")
        
        if results:
            return "\n\n".join(results)
            
        # Fallback for other engines
        return await page.inner_text("body")
    except Exception:
        return await page.inner_text("body")


# ── Tool handlers ─────────────────────────────────────────────────────

async def handle_browser_navigate(request: ToolCallRequest) -> ToolCallResponse:
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    if not url:
        return ToolCallResponse(success=False, error="Missing URL")

    content_type: str = request.args.get("content_type", "text")
    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(_cdp_url())
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms)

            title = await page.title()
            
            # Phase 100 Hardening: Handle search engines specifically
            if "google.com/search" in url or "duckduckgo.com" in url:
                content = await _extract_search_results(page)
            elif content_type == "html":
                content = await page.content()
            else:
                content = await page.inner_text("body")

            if len(content) > 12_000:
                content = content[:12_000]
                truncated = True
            else:
                truncated = False

            await page.close()
            await context.close()
            await browser.close()

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
        return ToolCallResponse(success=False, error=f"browser-navigate (async) failed: {exc}")


async def handle_browser_click(request: ToolCallRequest) -> ToolCallResponse:
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    selector = request.query or request.args.get("selector")
    if not url or not selector:
        return ToolCallResponse(success=False, error="Missing URL or selector")

    timeout_ms: int = int(request.args.get("timeout_ms", 10_000))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(_cdp_url())
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms * 3)
            await page.locator(selector).click(timeout=timeout_ms)
            result_url = page.url

            await page.close()
            await context.close()
            await browser.close()

        return ToolCallResponse(
            success=True,
            result={"url": url, "selector": selector, "result_url": result_url},
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-click (async) failed: {exc}")


async def handle_browser_evaluate(request: ToolCallRequest) -> ToolCallResponse:
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    expression = request.query or request.args.get("expression")
    if not url or not expression:
        return ToolCallResponse(success=False, error="Missing URL or expression")

    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(_cdp_url())
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms)
            result = await page.evaluate(expression)

            await page.close()
            await context.close()
            await browser.close()

        return ToolCallResponse(
            success=True,
            result={"url": url, "expression": expression, "value": result},
        )
    except Exception as exc:
        return ToolCallResponse(success=False, error=f"browser-evaluate (async) failed: {exc}")


async def handle_browser_screenshot(request: ToolCallRequest) -> ToolCallResponse:
    if not PLAYWRIGHT_AVAILABLE:
        return _unavailable()

    url = request.path or request.args.get("url")
    if not url:
        return ToolCallResponse(success=False, error="Missing URL")

    full_page: bool = bool(request.args.get("full_page", True))
    timeout_ms: int = int(request.args.get("timeout_ms", 30_000))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(_cdp_url())
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms)
            png_bytes: bytes = await page.screenshot(full_page=full_page)

            await page.close()
            await context.close()
            await browser.close()

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
        return ToolCallResponse(success=False, error=f"browser-screenshot (async) failed: {exc}")
