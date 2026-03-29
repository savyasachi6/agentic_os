import pytest
from agents.intent.classifier import classify_intent
from core.agent_types import Intent
from agents.capability_agent import CapabilityAgentWorker
from db.models import Node
from core.agent_types import AgentRole, NodeStatus, NodeType
import asyncio

def test_intent_links():
    assert classify_intent("what are links to this project") == Intent.CAPABILITY_QUERY
    assert classify_intent("show me the github url") == Intent.CAPABILITY_QUERY
    assert classify_intent("give me the documentation link") == Intent.CAPABILITY_QUERY

@pytest.mark.asyncio
async def test_capability_links_response():
    worker = CapabilityAgentWorker()
    task = Node(
        id=999,
        chain_id=1,
        agent_role=AgentRole.SCHEMA,
        type=NodeType.TASK,
        status=NodeStatus.PENDING,
        content="what are links to this project",
        payload={"query": "what are links to this project"}
    )
    
    # Mock tree_store to avoid DB calls in unit test
    class MockTreeStore:
        async def update_node_status_async(self, node_id, status, result):
            self.last_status = status
            self.last_result = result
            
    worker.tree_store = MockTreeStore()
    
    await worker._process_task(task)
    
    assert worker.tree_store.last_status == NodeStatus.DONE
    assert "## 🔗 Project Links" in worker.tree_store.last_result["message"]
    assert "https://github.com/savya6/agentic_os" in worker.tree_store.last_result["message"]

def test_intent_capabilities():
    assert classify_intent("what can you do") == Intent.CAPABILITY_QUERY
    assert classify_intent("list your skills") == Intent.CAPABILITY_QUERY
