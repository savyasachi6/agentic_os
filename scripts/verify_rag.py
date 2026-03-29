
import asyncio
import json
import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from db.queries.commands import TreeStore
from db.models import Node
from core.agent_types import NodeType, AgentRole, NodeStatus

async def main():
    store = TreeStore()
    
    # Create a session and chain
    session_id = "verification_session"
    chain = await store.create_chain_async(session_id, description="Verification Chain")
    
    # Create a RAG task
    node = await store.add_node_async(Node(
        chain_id=chain.id,
        type=NodeType.TASK,
        agent_role=AgentRole.RAG,
        payload={"query": "Who is the CEO of OpenAI?"},
        status=NodeStatus.PENDING
    ))
    
    print(f"Created node {node.id}. Waiting for worker...")
    
    # Wait for completion
    for _ in range(60):
        await asyncio.sleep(2)
        updated = await store.get_node_by_id_async(node.id)
        print(f"Status: {updated.status}")
        if updated.status in (NodeStatus.DONE, NodeStatus.FAILED):
            print("Result:", updated.result)
            break

if __name__ == "__main__":
    asyncio.run(main())
