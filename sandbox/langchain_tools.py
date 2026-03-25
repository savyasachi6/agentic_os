"""
LangChain Tools Wrapper for Agentic OS Sandbox

This module wraps LangChain community tools (e.g., Wikipedia, WebBaseLoader, Arxiv) 
into standard Agentic OS ToolCallResponse handlers. 
This allows the custom ReAct loop and hardware-optimized LLMRouter to remain untouched, 
while granting agents access to a vast library of external capabilities.

Hardware Assumptions:
- Runs in the isolated Sandbox FastAPI worker, completely decoupled from the TensorRT batching loop.
- Network bound, light memory footprint.
"""

import sys
try:
    from langchain_community.tools import WikipediaQueryRun  # type: ignore
    from langchain_community.utilities import WikipediaAPIWrapper  # type: ignore
    from langchain_community.document_loaders import WebBaseLoader  # type: ignore
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("[langchain_tools] Warning: langchain-community not installed. Tools will be disabled.", file=sys.stderr)

# Import the wire models from the lightweight models module
from .models import ToolCallRequest, ToolCallResponse  # type: ignore

def handle_wikipedia_search(request: ToolCallRequest) -> ToolCallResponse:
    """Execute a Wikipedia search using LangChain."""
    if not LANGCHAIN_AVAILABLE:
        return ToolCallResponse(success=False, error="langchain-community is not installed in the worker environment.")
        
    query = request.query or request.args.get("query")
    if not query:
        return ToolCallResponse(success=False, error="Missing 'query' parameter for wikipedia search.")

    try:
        api_wrapper = WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=2000)
        tool = WikipediaQueryRun(api_wrapper=api_wrapper)
        result_text = tool.run(query)
        
        return ToolCallResponse(
            success=True,
            result={
                "query": query,
                "content": result_text
            }
        )
    except Exception as e:
        return ToolCallResponse(success=False, error=f"Wikipedia tool failed: {str(e)}")


def handle_web_scrape(request: ToolCallRequest) -> ToolCallResponse:
    """Scrape a webpage URL using LangChain's WebBaseLoader."""
    if not LANGCHAIN_AVAILABLE:
        return ToolCallResponse(success=False, error="langchain-community is not installed in the worker environment.")
        
    url = request.path or request.args.get("url")
    if not url:
        return ToolCallResponse(success=False, error="Missing 'url' or 'path' parameter for web scraping.")
        
    try:
        loader = WebBaseLoader(url)
        docs = loader.load()
        # Combine docs into a single text block, truncated to prevent context window overflow
        full_text = "\n\n".join([d.page_content for d in docs])
        # Safety truncation: assuming Qwen 7B context limits, keep this reasonable for the LLMRouter
        truncated_text = full_text[:8000] if len(full_text) > 8000 else full_text
        
        return ToolCallResponse(
            success=True,
            result={
                "url": url,
                "content": truncated_text,
                "truncated": len(full_text) > 8000
            }
        )
    except Exception as e:
        return ToolCallResponse(success=False, error=f"Web Scraper tool failed: {str(e)}")

# Add more LangChain wrapped tools here as needed.
