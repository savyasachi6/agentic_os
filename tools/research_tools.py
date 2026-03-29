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
    description: str = "Search the live web for real-time news, headlines, and data using Brave Search."
    parameters: str = "query: str, count: int (default: 5)"
    
    query: str = Field(default="", description="The search query string.")
    count: int = Field(default=5, description="Number of results to retrieve.")

    def run(self) -> str:
        # Note: This is a synchronous call wrapped for the registry.
        # RAGAgentWorker should call .run_action to handle async tools.
        return "web_search requires run_async"

    async def run_async(self, **kwargs) -> ActionResult:
        query = kwargs.get("query", self.query)
        count = kwargs.get("count", self.count)
        
        api_key = settings.brave_search_api_key
        if not api_key:
            return ActionResult(success=False, error_trace="Brave Search API key is missing. Set BRAVE_SEARCH_API_KEY.")

        # Strip action tags if passed by mistake
        if isinstance(query, str):
            query = query.replace("<action>", "").replace("</action>", "").strip()

        url = f"https://api.search.brave.com/res/v1/web/search?q={query}&count={count}"
        headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                results = []
                for result in data.get("web", {}).get("results", []):
                    results.append(f"- **{result['title']}**\n  URL: {result['url']}\n  Snippet: {result['description']}")
                
                if not results:
                    return ActionResult(success=True, data={"output": f"No results found for query: {query}"})
                
                return ActionResult(success=True, data={"output": "\n\n".join(results)})
        except Exception as e:
            logger.error(f"Brave Search failed: {e}")
            return ActionResult(success=False, error_trace=str(e))

class WebScrapeAction(BaseAction):
    name: str = "web_scrape"
    description: str = "Fetch the full text content of a specific webpage and convert it to markdown."
    parameters: str = "url: str"
    
    url: str = Field(default="", description="The full URL of the webpage to scrape.")

    def run(self) -> str:
        return "web_scrape requires run_async"

    async def run_async(self, **kwargs) -> ActionResult:
        url = kwargs.get("url", self.url)
        browser_url = settings.browser_ws_url or "ws://browserless:9222"
        
        # Simple scraping fallback via httpx if browserless is not needed for JS
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                from markdownify import markdownify
                text = markdownify(response.text).strip()
                
                if len(text) > 10000:
                    text = text[:10000] + "\n\n... [Content Truncated]"
                
                return ActionResult(success=True, data={"output": text})
        except Exception as e:
            logger.warning(f"Direct scrape failed for {url}. Reason: {e}")
            return ActionResult(success=False, error_trace=f"Failed to scrape URL: {str(e)}")

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
