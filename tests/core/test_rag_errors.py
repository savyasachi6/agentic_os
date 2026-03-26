import pytest
import asyncio
from unittest.mock import AsyncMock
from agents.rag_agent import ResearchAgentWorker
from db.models import Node
from agent_core.agent_types import AgentRole, NodeStatus, NodeType

@pytest.mark.asyncio
async def test_rag_max_turns_error():
    worker = ResearchAgentWorker()
    worker.tree_store = AsyncMock()
    
    task = Node(
        id=456,
        chain_id=1,
        agent_role=AgentRole.RAG,
        type=NodeType.TASK,
        status=NodeStatus.PENDING,
        content="Research quantum computing.",
        payload={"max_turns": 1}
    )
    
    # Mock LLM to always return a search action, hitting max turns
    worker.llm.generate_async = AsyncMock(return_value="Action: hybrid_search({\"query\": \"quantum\"})")
    worker.retriever.retrieve_context_async = AsyncMock(return_value="Some context")
    
    await worker._process_task(task)
    
    # Verify it failed with max_turns error_type
    worker.tree_store.update_node_status_async.assert_called()
    args, kwargs = worker.tree_store.update_node_status_async.call_args
    assert args[1] == NodeStatus.FAILED
    assert kwargs["result"]["error_type"] == "max_turns"

@pytest.mark.asyncio
async def test_rag_critical_failure_error():
    worker = ResearchAgentWorker()
    worker.tree_store = AsyncMock()
    
    task = Node(id=789, chain_id=1, agent_role=AgentRole.RAG, type=NodeType.TASK, status=NodeStatus.PENDING)
    
    # Force a crash
    worker.llm.generate_async = AsyncMock(side_effect=Exception("LLM Crash"))
    
    await worker._process_task(task)
    
    worker.tree_store.update_node_status_async.assert_called()
    args, kwargs = worker.tree_store.update_node_status_async.call_args
    assert args[1] == NodeStatus.FAILED
    assert kwargs["result"]["error_type"] == "critical_failure"
