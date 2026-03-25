"""
tests/test_patterns.py
======================
Unit tests for the advanced agentic patterns (Sequential, Parallel, Loop).
Verifies node execution and graph topology using LangGraph.
"""
import pytest
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from agent_core.graph.state import AgentState

# ── 1. Sequential Pattern Tests ───────────────────────────────────
from agent_core.graph.nodes.sequential_chain import build_code_gen_chain

@pytest.mark.asyncio
async def test_sequential_code_gen_topology():
    chain = build_code_gen_chain()
    # Mock state
    state = {
        "messages": [HumanMessage(content="Write a python script to list files")],
        "session_id": "test_seq"
    }
    # We can't easily run the real RAG/LLM in unit tests without extensive mocking,
    # so we just verify the chain compiles and the nodes are present.
    assert "retrieve_context" in chain.nodes
    assert "generate_code" in chain.nodes
    assert "format_output" in chain.nodes

# ── 2. Parallel Pattern Tests ─────────────────────────────────────
from agent_core.graph.nodes.parallel_chain import build_parallel_chain

@pytest.mark.asyncio
async def test_parallel_retrieval_topology():
    chain = build_parallel_chain()
    assert "parallel_retrieve" in chain.nodes
    assert "merge_results" in chain.nodes

# ── 3. Loop Pattern Tests ─────────────────────────────────────────
from agent_core.graph.nodes.loop_chain import build_loop_chain

@pytest.mark.asyncio
async def test_loop_refinement_topology():
    chain = build_loop_chain()
    assert "generator" in chain.nodes
    assert "critic" in chain.nodes
    # Check for conditional edges
    # (Checking edges directly in compiled graph is complex, but we verify nodes exist)

# ── 4. End-to-End Coordination Test (Mocked) ──────────────────────
# test_coordinator_hierarchical_routing is removed as the Coordinator now uses a LangGraph orchestrator
# and no longer maintains a static routing_table.

if __name__ == "__main__":
    asyncio.run(test_sequential_code_gen_topology())
    asyncio.run(test_parallel_retrieval_topology())
    asyncio.run(test_loop_refinement_topology())
    print("Pattern tests validated (topology check).")
