"""
core/graph/nodes/parallel_chain.py
====================================
Parallel Fan-Out / Fan-In Pattern
Used when: Multiple independent data sources need to be queried
Flow: split → [rag_lookup || web_search || sql_lookup] → merge
"""
import asyncio
from typing import List, Dict, Any
from langgraph.graph import StateGraph, END
from agent_core.graph.state import AgentState
from agent_core.llm.client import LLMClient

# ── Fan-Out: Run all sub-agents concurrently ──────────────────────
async def parallel_retrieve(state: AgentState) -> dict:
    """
    Simultaneously queries:
    - RAG (pgvector semantic search)
    - SQL (structured capability/skill lookup)
    - Web (live news/current events) — optional, based on flag
    """
    if not state.get("messages"):
        return {"parallel_results": {}}
        
    query = state["messages"][-1].content if hasattr(state["messages"][-1], "content") else str(state["messages"][-1])

    # Build task list — all run at the same time
    tasks = [
        _rag_lookup(query),
        _sql_lookup(query),
    ]

    # Add web search only if flagged in state or if it's a web intent
    if state.get("needs_web_search", False):
        tasks.append(_web_search(query))

    # asyncio.gather = run ALL simultaneously, wait for ALL
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Store each result in state
    parallel_results = {
        "rag": results[0] if not isinstance(results[0], Exception) else f"RAG Error: {results[0]}",
        "sql": results[1] if not isinstance(results[1], Exception) else f"SQL Error: {results[1]}",
    }
    
    if len(results) > 2:
        parallel_results["web"] = results[2] if not isinstance(results[2], Exception) else f"Web Error: {results[2]}"

    return {"parallel_results": parallel_results}


# ── Fan-In: Merge agent synthesizes all results ───────────────────
async def merge_results(state: AgentState) -> dict:
    """
    Merger LLM: takes all parallel results and synthesizes
    a single coherent answer. Does NOT re-search.
    """
    results = state.get("parallel_results", {})
    if not state.get("messages"):
        return {"messages": []}
        
    query = state["messages"][-1].content if hasattr(state["messages"][-1], "content") else str(state["messages"][-1])

    # Build merger prompt with all collected evidence
    merger_prompt = f"""You are a synthesis agent for Agentic OS. Your task is to combine information from multiple sources into one clear, high-quality answer.

USER QUESTION: {query}

RAG KNOWLEDGE BASE RESULTS:
{results.get('rag', 'No results found.')}

STRUCTURED DATA (SQL) RESULTS:
{results.get('sql', 'No results found.')}

WEB SEARCH RESULTS:
{results.get('web', 'Web search was not performed.')}

RULES:
1. SYNTHESIZE: Do not repeat each source verbatim. Merge them into a cohesive narrative.
2. CONFLICT RESOLUTION: If sources contradict, note the discrepancy clearly.
3. RELEVANCE: If a source provided irrelevant information, ignore it.
4. UNIFIED ANSWER: Provide ONE comprehensive and coherent final response.
"""
    llm = LLMClient()
    answer = await llm.generate_async([
        {"role": "system", "content": merger_prompt}
    ])

    from langchain_core.messages import AIMessage
    return {"messages": [AIMessage(content=answer)]}


def build_parallel_chain() -> StateGraph:
    """
    Constructs the parallel orchestration graph.
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("parallel_retrieve", parallel_retrieve)
    workflow.add_node("merge_results", merge_results)

    workflow.set_entry_point("parallel_retrieve")
    workflow.add_edge("parallel_retrieve", "merge_results")
    workflow.add_edge("merge_results", END)

    return workflow.compile()


# ── Sub-agent implementations ─────────────────────────────────────
async def _rag_lookup(query: str) -> str:
    """Semantic context retrieval via HybridRetriever."""
    from agent_core.rag.retriever import HybridRetriever
    try:
        retriever = HybridRetriever()
        results = await retriever.retrieve_async(query, top_k=3)
        return "\n".join([r.content for r in results]) if results else "No specific matches found in knowledge base."
    except Exception as e:
        return f"RAG lookup failed: {e}"

async def _sql_lookup(query: str) -> str:
    """Structured search for skills and capabilities."""
    from db.queries.commands import TreeStore
    try:
        store = TreeStore()
        # Search skills/capabilities via structured SQL
        results = store.search_skills(query)
        return str(results) if results else "No matching structured capabilities found."
    except Exception as e:
        return f"SQL lookup failed: {e}"

async def _web_search(query: str) -> str:
    """Stub for web search tool."""
    # For now, we reuse the existing RAG agent logic for news if available, or placeholder
    return f"Live web search results for '{query}' would be retrieved here via Brave/Puppeteer MCP."
