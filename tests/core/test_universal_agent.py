import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agent_core.agents.universal_agent import UniversalAgentWorker
from agent_memory.models import Node, AgentRole, NodeType, NodeStatus

@pytest.fixture
def mock_tree_store():
    with patch('agent_core.agents.universal_agent.TreeStore') as mock:
        store = mock.return_value
        store.update_node_status = AsyncMock()
        yield store

@pytest.fixture
def mock_skill_retriever():
    with patch('agent_core.agents.universal_agent.SkillRetriever') as mock:
        retriever = mock.return_value
        retriever.retrieve_context = MagicMock(return_value="## Instructions\n1. Use shell_execute to echo 'Hello'\n2. respond(Done)")
        yield retriever

@pytest.fixture
def mock_llm():
    with patch('agent_core.agents.universal_agent.LLMClient') as mock:
        client = mock.return_value
        client.generate_async = AsyncMock()
        yield client

@pytest.mark.asyncio
async def test_universal_agent_process_task(mock_tree_store, mock_skill_retriever, mock_llm):
    """Verify that UniversalAgentWorker can process a specialist task using skills."""
    worker = UniversalAgentWorker()
    
    # Mock task
    task = Node(
        id=123,
        chain_id=1,
        agent_role=AgentRole.SPECIALIST,
        type=NodeType.TOOL_CALL,
        content="Delegating to theme_factory: Generate a dark theme",
        payload={"query": "Generate a dark theme", "max_turns": 5}
    )
    
    # Mock LLM sequence: 1. call shell, 2. respond
    mock_llm.generate_async.side_effect = [
        "Thought: I need to use shell to echo. Action: shell_execute(echo 'Success')",
        "Thought: Task done. Action: respond(Completed successfully)"
    ]
    
    # Mock shell execution
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout="Success", stderr="", returncode=0)
        
        await worker._process_task(task)
        
        # Verify status updates
        mock_tree_store.update_node_status.assert_called_with(
            123, NodeStatus.DONE, result={"message": "Completed successfully"}
        )
        
        # Verify skill retrieval was called
        mock_skill_retriever.retrieve_context.assert_called_once_with("Generate a dark theme")

@pytest.mark.asyncio
async def test_universal_agent_max_iterations(mock_tree_store, mock_skill_retriever, mock_llm):
    """Verify that UniversalAgentWorker fails after max_turns."""
    worker = UniversalAgentWorker()
    task = Node(
        id=456,
        chain_id=1,
        agent_role=AgentRole.SPECIALIST,
        type=NodeType.TOOL_CALL,
        content="Delegating to slow_skill: Wait",
        payload={"query": "Wait forever", "max_turns": 2}
    )
    
    mock_llm.generate_async.return_value = "Thought: Still waiting. Action: shell_execute(sleep 1)"
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        await worker._process_task(task)
        
        mock_tree_store.update_node_status.assert_any_call(
            456, NodeStatus.FAILED, result={"error": "Max iterations reached"}
        )
