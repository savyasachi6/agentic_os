"""
tools/research_tools.py
=======================
Official OS-level tools for web search and scraping.
Formally registers 'web_search' and 'web_scrape' with the ToolRegistry.
"""

import httpx
import logging
import json
from pydantic import Field
from .base import BaseAction, ActionResult
from core.tool_registry import registry
from core.settings import settings

logger = logging.getLogger("agentos.tools.research")

class WebSearchAction(BaseAction):
    name: str = "web_search"
    description: str = (
        "Search the live web for real-time news, headlines, and data. "
        "Uses DuckDuckGo (no API key required). Falls back to httpx if browser is unavailable."
    )
    parameters: str = "query: str, count: int (default: 5)"

    query: str = Field(default="", description="The search query string.")
    count: int = Field(default=5, description="Number of results to retrieve.")

    def run(self) -> str:
        return "web_search requires run_async"

    async def run_async(self, **kwargs) -> ActionResult:
        query   = kwargs.get("query", self.query)
        count   = kwargs.get("count", self.count)

        if isinstance(query, str):
            query = query.replace("<action>", "").replace("</action>", "").strip()

        # ── Strategy 1: Brave Search API (if key is configured) ─────────────────
        api_key = settings.brave_search_api_key
        if api_key:
            try:
                url     = f"https://api.search.brave.com/res/v1/web/search?q={query}&count={count}"
                headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data    = resp.json()
                    results = [
                        f"- **{r['title']}**\n  URL: {r['url']}\n  {r.get('description','')}"
                        for r in data.get("web", {}).get("results", [])
                    ]
                    if results:
                        return ActionResult(success=True, data={"output": "\n\n".join(results[:count])})
            except Exception as e:
                logger.warning(f"Brave Search failed, falling back to DuckDuckGo: {e}")

        # ── Strategy 2: DuckDuckGo JSON API (Instant Answers) ────────────────────
        try:
            ddg_api_url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(ddg_api_url, params=params)
                r.raise_for_status()
                data = r.json()
                
                results = []
                # Instant Answer (Abstract)
                if data.get("AbstractText"):
                    results.append(f"- **{data.get('Heading', 'Abstract')}**\n  URL: {data.get('AbstractURL')}\n  {data.get('AbstractText')}")
                
                # Related Topics
                for item in data.get("RelatedTopics", []):
                    if len(results) >= count: break
                    if "Text" in item and "FirstURL" in item:
                        results.append(f"- **{item['Text'][:80]}...**\n  URL: {item['FirstURL']}\n  {item['Text']}")
                
                if results:
                    logger.info(f"[web_search] Found {len(results)} results via DDG API")
                    return ActionResult(success=True, data={"output": "\n\n".join(results)})
        except Exception as e:
            logger.warning(f"[web_search] DDG API failed, trying lightpanda: {e}")

        # ── Strategy 3: Fallback — httpx GET to DuckDuckGo HTML ─────────────────
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AgenticOS/2.7; +https://github.com/savyasachi6/agentic_os)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                resp = await client.get(ddg_url)
                resp.raise_for_status()
                from markdownify import markdownify
                text = markdownify(resp.text).strip()
                # Extract only the result blocks to keep it clean
                if "result__title" in resp.text or "result__a" in resp.text:
                    from bs4 import BeautifulSoup
                    soup    = BeautifulSoup(resp.text, "html.parser")
                    results = []
                    # Try multiple potential result selectors
                    for r in (soup.select(".result") or soup.select(".links_main"))[:count]:
                        title_el   = r.select_one(".result__title a") or r.select_one(".result__a")
                        snippet_el = r.select_one(".result__snippet")
                        if title_el:
                            results.append(
                                f"- **{title_el.get_text().strip()}**\n"
                                f"  URL: {title_el.get('href', '')}\n"
                                f"  {snippet_el.get_text().strip() if snippet_el else ''}"
                            )
                    if results:
                        return ActionResult(success=True, data={"output": "\n\n".join(results)})
                # Last resort — raw markdown of page
                return ActionResult(success=True, data={"output": text[:8000]})
        except Exception as e3:
            logger.error(f"[web_search] All search strategies failed: {e3}")
            return ActionResult(success=False, error_trace=f"All search strategies failed: {e3}")


class WebScrapeAction(BaseAction):
    name: str = "web_scrape"
    description: str = "Fetch the full text content of a specific webpage and convert it to markdown."
    parameters: str = "url: str"
    
    url: str = Field(default="", description="The full URL of the webpage to scrape.")

    def run(self) -> str:
        return "web_scrape requires run_async"

    async def run_async(self, **kwargs) -> ActionResult:
        url = kwargs.get("url", self.query)  # Note: query is inherited from BaseAction if used loosely
        if not url or url == "self": # Guard against common mis-passes
            url = kwargs.get("url") or self.url
            
        browser_url = settings.browser_ws_url or "ws://lightpanda:9222"
        from markdownify import markdownify
        
        # Strategy 1: Real headless browser via Playwright
        try:
            import playwright.async_api as pw
            async with pw.async_playwright() as p:
                logger.info(f"[web_scrape] Connecting to browser at {browser_url}")
                # Use connect() for generic WS instead of connect_over_cdp if CDP is flaky
                browser = await p.chromium.connect(browser_url)
                page = await browser.new_page()
                
                await page.goto(url, wait_until="networkidle", timeout=30000)
                content = await page.content()
                await browser.close()
                
                text = markdownify(content).strip()
                if len(text) > 15000:
                    text = text[:15000] + "\n\n... [Content Truncated]"
                
                return ActionResult(success=True, data={"output": text})
        except Exception as e:
            logger.warning(f"[web_scrape] Browser scrape failed for {url}: {e}. Trying httpx fallback.")
            
            # Strategy 2: Simple HTTP extraction for static sites
            try:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; AgenticOS/2.7; +https://github.com/savyasachi6/agentic_os)"}
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    text = markdownify(response.text).strip()
                    
                    if len(text) > 10000:
                        text = text[:10000] + "\n\n... [Content Truncated]"
                    
                    return ActionResult(success=True, data={"output": text})
            except Exception as e2:
                logger.error(f"[web_scrape] All scrape strategies failed: {e2}")
                return ActionResult(success=False, error_trace=f"Failed to scrape URL: {str(e2)}")

# Safe Registration (Phase 62): Instantiate objects once to access their descriptions and async runners safely
_search_tool = WebSearchAction()
_scrape_tool = WebScrapeAction()

registry.register(
    "web_search", 
    _search_tool.run_async, 
    _search_tool.description,
    {"parameters": {"query": {"type": "string", "required": True}, "count": {"type": "integer", "required": False}}}
)

registry.register(
    "web_scrape", 
    _scrape_tool.run_async, 
    _scrape_tool.description,
    {"parameters": {"url": {"type": "string", "required": True}}}
)
