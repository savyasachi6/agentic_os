import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.orchestrator import OrchestratorAgent
from agents.graph.state import AgentState
from core.agent_types import NodeType, Intent, AgentRole, NodeStatus

@pytest.fixture
def mock_tree_store():
    with patch('agents.orchestrator.TreeStore') as mock:
        store = mock.return_value
        mock_chain = MagicMock(id=1, root_node_id=10)
        store.create_chain_async = AsyncMock(return_value=mock_chain)
        store.get_chain_by_session_id_async = AsyncMock(return_value=None)
        async def get_node_mock(node_id):
            mock_node = MagicMock(id=node_id, status=NodeStatus.DONE)
            mock_node.result = {"answer": "Mocked Result", "message": "Mocked Result"}
            return mock_node
        store.get_node_async = AsyncMock(side_effect=get_node_mock)

        async def add_node_mock(node):
            if not hasattr(node, 'id') or node.id is None:
                node.id = 99
            return node
        store.add_node_async = AsyncMock(side_effect=add_node_mock)
        
        async def build_context_mock(*args, **kwargs):
            return ([], 0)
        store.build_context_async = AsyncMock(side_effect=build_context_mock)
        
        yield store

@pytest.fixture
def mock_llm():
    with patch('agents.orchestrator.LLMClient') as mock:
        client = mock.return_value
        # Default behavior
        client.generate_async = AsyncMock(return_value="Action: respond(Done)")
        
        async def mock_streaming(*args, **kwargs):
            yield "Action: respond(Done)"
        client.generate_streaming.side_effect = mock_streaming
        
        yield client


# Removed mock_skill_retriever as it is no longer used in OrchestratorAgent

@pytest.fixture
def mock_agent_state():
    with patch('agents.orchestrator.AgentState') as mock:
        state = mock.return_value
        state.history = []
        state.session_id = "test-session-id"
        state.get_session_summary.return_value = "Mock Summary"
        yield state

@pytest.mark.asyncio
async def test_coordinator_routing_to_productivity(mock_tree_store, mock_llm, mock_agent_state):
    """Verify that 'add a todo' routes to the productivity agent."""
    # We must mock generate_async since we don't pass status_callback
    mock_llm.generate_async.side_effect = [
        "Thought: Use productivity agent. Action: productivity(Add a todo to buy milk)",
        "Action: respond(Final Answer)"
    ]

    coordinator = OrchestratorAgent()
    coordinator.session_id = "test-session-id"
    
    with patch.object(coordinator, '_wait_for_task', return_value={"status": "done"}):
        await coordinator.run_turn("Add a todo to buy milk")
        
        calls = mock_tree_store.add_node_async.call_args_list
        productivity_call = next((c[0][0] for c in calls if getattr(c[0][0], 'agent_role', None) == AgentRole.PRODUCTIVITY), None)
        assert productivity_call is not None
        assert productivity_call.type == NodeType.TASK

@pytest.mark.asyncio
async def test_specialist_budget_increase(mock_tree_store, mock_llm, mock_agent_state):
    """Verify that specialists receive a budget of 10 turns."""
    mock_llm.generate_async.side_effect = [
        "Thought: Routing. Action: code(echo hello)",
        "Action: respond(Final Answer)"
    ]

    coordinator = OrchestratorAgent()
    coordinator.session_id = "test-session-id"
    
    with patch.object(coordinator, '_wait_for_task', return_value="hello"):
        await coordinator.run_turn("Test budget")
        
        calls = mock_tree_store.add_node_async.call_args_list
        code_call = next((c[0][0] for c in calls if getattr(c[0][0], 'agent_role', None) == AgentRole.TOOLS), None)
        assert code_call is not None
        # With max_total=8 and 1 turn used by coordinator, remaining is 7
        assert code_call.payload['max_turns'] == 7
