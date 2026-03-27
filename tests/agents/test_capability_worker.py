import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from agent_core.agent_types import AgentRole, NodeStatus, NodeType
from db.models import Node
from agent_core.agents.capability_agent import CapabilityAgentWorker

@pytest.mark.asyncio
async def test_capability_worker_completion_recognition():
    """Verify that CapabilityAgentWorker recognizes both 'respond' and 'complete_task'."""
    worker = CapabilityAgentWorker()
    worker.llm = AsyncMock()
    worker.tree_store = AsyncMock()
    worker.cache = AsyncMock()
    worker.cache.get_cached_response_async.return_value = None
    
    # Mock task with all required fields
    task = Node(
        id=1, 
        chain_id=100, 
        agent_role=AgentRole.SCHEMA, 
        type=NodeType.TASK,
        payload={"query": "what can you do?"}, 
        status=NodeStatus.PENDING
    )
    
    # Case 1: respond(...)
    worker.llm.generate_async.side_effect = [
        "Thought: I will answer.\nAction: respond(I can help with database queries.)"
    ]
    await worker._process_task(task)
    worker.tree_store.update_node_status_async.assert_called_with(1, NodeStatus.DONE, result={"message": "I can help with database queries."})
    
    # Case 2: complete_task(...)
    worker.llm.generate_async.side_effect = [
        "Thought: I am done.\nAction: complete_task(Found the tools.)"
    ]
    await worker._process_task(task)
    worker.tree_store.update_node_status_async.assert_called_with(1, NodeStatus.DONE, result={"message": "Found the tools."})

@pytest.mark.asyncio
async def test_capability_worker_sql_execution():
    """Verify that CapabilityAgentWorker executes SQL and observes results."""
    worker = CapabilityAgentWorker()
    worker.llm = AsyncMock()
    worker.tree_store = AsyncMock()
    worker.cache = AsyncMock()
    worker.cache.get_cached_response_async.return_value = None
    
    # Mock DB execution
    with patch.object(worker, '_execute_query', return_value={"success": True, "rows": [{"name": "test_tool"}]}):
        task = Node(
            id=2, 
            chain_id=101, 
            agent_role=AgentRole.SCHEMA, 
            type=NodeType.TASK,
            payload={"query": "list tools"}, 
            status=NodeStatus.PENDING
        )
        
        worker.llm.generate_async.side_effect = [
            "Thought: I need to query tools.\nAction: sql_query(SELECT name FROM tools)",
            "Thought: I see the tool.\nAction: respond(Tool: test_tool)"
        ]
        
        await worker._process_task(task)
        
        # Verify it went through two turns
        assert worker.llm.generate_async.call_count == 2
        worker.tree_store.update_node_status_async.assert_called_with(2, NodeStatus.DONE, result={"message": "Tool: test_tool"})
