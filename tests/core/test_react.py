import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.agent_types import NodeType

@pytest.fixture
def mock_tree_store():
    with patch('agents.coordinator.AgentState') as mock:
        store = mock.return_value
        mock_chain = MagicMock(id=1, root_node_id=10)
        store.create_chain.return_value = mock_chain
        store.get_chain_by_session_id.return_value = None
        
        async def add_node_mock(node):
            node.id = 99
            return node
        store.add_node_async.side_effect = add_node_mock
        
        async def build_context_mock(*args, **kwargs):
            return ([], 0)
        store.build_context_async.side_effect = build_context_mock
        
        yield store

@pytest.fixture
def mock_llm():
    with patch('agents.coordinator.LLMClient') as mock:
        client = mock.return_value
        client.generate_async = AsyncMock(return_value="Thought: Done. Action: respond(Final Answer)")
        yield client

@pytest.fixture
def mock_skill_retriever():
    with patch('agents.coordinator.SkillRetriever') as mock:
        retriever = mock.return_value
        retriever.retrieve_context.return_value = "Mock Skill Context"
        yield retriever

@pytest.fixture
def mock_agent_state():
    with patch('agents.coordinator.AgentState') as mock:
        state = mock.return_value
        state.history = []
        state.session_id = "test-session-id"
        state.get_session_summary.return_value = "Mock Summary"
        yield state

@pytest.mark.asyncio
async def test_direct_final_answer(mock_tree_store, mock_llm, mock_skill_retriever, mock_agent_state):
    mock_llm.generate_async.return_value = "Thought: I have the answer.\nAction: respond(Paris is the capital of France.)"
    
    agent = CoordinatorAgent()
    response = await agent.run_turn("What is the capital of France?")
    assert "Paris" in response

@pytest.mark.asyncio
async def test_tool_dispatch_shell(mock_tree_store, mock_llm, mock_skill_retriever, mock_agent_state):
    mock_llm.generate_async.side_effect = [
        "Thought: I will run a command.\nAction: code(echo hello)",
        "Action: respond(Final answer: hello)"
    ]
    
    agent = CoordinatorAgent()
    with patch.object(agent, '_wait_for_task', new_callable=AsyncMock, return_value="hello"):
        response = await agent.run_turn("Say hello")
        assert "hello" in response

@pytest.mark.asyncio
async def test_tool_dispatch_read_file(mock_tree_store, mock_llm, mock_skill_retriever, mock_agent_state):
    mock_llm.generate_async.side_effect = [
        "Thought: I will read the file.\nAction: code(read_file test.txt)",
        "Action: respond(File content was: hello world)"
    ]
    
    agent = CoordinatorAgent()
    with patch.object(agent, '_wait_for_task', new_callable=AsyncMock, return_value="hello world"):
        response = await agent.run_turn("Read test.txt")
        assert "hello world" in response
