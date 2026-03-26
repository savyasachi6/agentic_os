import pytest
import asyncio
from agents.planner import PlannerAgentWorker
from db.models import Node
from agent_core.agent_types import AgentRole, NodeStatus, NodeType

@pytest.mark.asyncio
async def test_planner_worker_processing():
    worker = PlannerAgentWorker()
    
    # Mock tree_store to avoid DB calls
    class MockTreeStore:
        def __init__(self):
            self.last_status = None
            self.last_result = None
            
        async def update_node_status_async(self, node_id, status, result):
            self.last_status = status
            self.last_result = result
            
    worker.tree_store = MockTreeStore()
    
    task = Node(
        id=123,
        chain_id=1,
        agent_role=AgentRole.PLANNER,
        type=NodeType.TASK,
        status=NodeStatus.PENDING,
        content="Decompose this task: Write a blog post about AI."
    )
    
    from unittest.mock import AsyncMock
    worker.llm.generate_async = AsyncMock(return_value="Plan: 1. Research 2. Write 3. Publish")
    
    await worker._process_task(task)
    
    assert worker.tree_store.last_status == NodeStatus.DONE
    assert "plan" in worker.tree_store.last_result
