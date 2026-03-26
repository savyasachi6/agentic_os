import asyncio
import sys
import os

# Ensure root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agents.capability_agent import CapabilityAgentWorker
from db.models import Node
from agent_core.agent_types import AgentRole, NodeType

async def test_capability():
    worker = CapabilityAgentWorker()
    # Mock node
    task = Node(
        id=999,
        chain_id=1,
        agent_role=AgentRole.SCHEMA,
        type=NodeType.TASK,
        payload={"query": "what skills needed for agent creation"}
    )
    
    # We need to mock tree_store.update_node_status_async
    from unittest.mock import AsyncMock
    worker.tree_store.update_node_status_async = AsyncMock()
    
    print("Testing 'what skills needed for agent creation'...")
    await worker._process_task(task)
    
    args, kwargs = worker.tree_store.update_node_status_async.call_args
    status = args[1]
    result = kwargs.get("result", {})
    print(f"Status: {status}")
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_capability())
