import pytest
from unittest.mock import patch, MagicMock
from agent_core.intent.classifier import classify_intent
from agent_core.agent_types import Intent
from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.graph.state import AgentState

def test_intent_classification_logic():
    # Test narrowing: "explain the architecture" should be LLM_DIRECT
    assert classify_intent("explain the architecture") == Intent.LLM_DIRECT
    
    # Test task detection: "set up a new postgres database" should be COMPLEX_TASK
    # (previously might have been LLM_DIRECT)
    assert classify_intent("set up a new postgres database") == Intent.COMPLEX_TASK
    
    # Test fast-paths
    assert classify_intent("hello") == Intent.GREETING
    assert classify_intent("what are your skills?") == Intent.CAPABILITY_QUERY

@pytest.mark.asyncio
async def test_coordinator_guard_preservation():
    """Verify that the AgentCallGuard is passed to the graph and used."""
    with patch("agent_core.graph.coordinator_graph.build_coordinator_graph") as mock_build, \
         patch("db.queries.commands.TreeStore") as mock_tree_store, \
         patch("agents.coordinator.classify_intent") as mock_classify:
        
        mock_graph = MagicMock()
        mock_build.return_value = mock_graph
        mock_classify.return_value = Intent.COMPLEX_TASK
        
        agent = CoordinatorAgent()
        # Mock tree store to avoid DB calls
        agent.tree_store = mock_tree_store
        agent.chain_id = 99
        
        # Initial call
        await agent.run_turn("Test complex task")
        
        # Check that the graph was called with a guard in the state
        args, kwargs = mock_graph.ainvoke.call_args
        initial_state = args[0]
        assert "guard" in initial_state
        assert initial_state["guard"].max_total == 8
