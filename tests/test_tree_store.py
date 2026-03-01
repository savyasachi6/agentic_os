import pytest
from datetime import datetime
from agent_memory.db import init_schema, get_db_connection
from agent_memory.models import Chain, Node, AgentRole, NodeType, NodeStatus
from agent_memory.tree_store import TreeStore

class DummyVectorStore:
    def generate_embedding(self, text: str):
        # Return a dummy vector of length 768
        return [0.0] * 768

@pytest.fixture(scope="module")
def setup_db():
    init_schema()

def test_tree_crud_and_queue(setup_db):
    store = TreeStore(vector_store=DummyVectorStore())
    
    # 1. Create a chain
    chain = store.create_chain(session_id="test_sess_1", description="Test Chain")
    assert chain.id is not None
    
    # 2. Add some nodes
    root = store.add_node(Node(
        chain_id=chain.id,
        agent_role=AgentRole.ORCHESTRATOR,
        type=NodeType.PLAN,
        content="Root plan",
        priority=10
    ))
    assert root.id is not None
    
    child1 = store.add_node(Node(
        chain_id=chain.id,
        parent_id=root.id,
        agent_role=AgentRole.TOOLS,
        type=NodeType.TOOL_CALL,
        content="Fetch data",
        priority=5,
        planned_order=1
    ))
    
    child2 = store.add_node(Node(
        chain_id=chain.id,
        parent_id=root.id,
        agent_role=AgentRole.RAG,
        type=NodeType.LLM_CALL,
        content="Summarize",
        priority=8,
        planned_order=2
    ))
    
    # 3. Test Queue Order
    nxt = store.get_next_pending_node(chain.id)
    # Highest priority first
    assert nxt.id == root.id
    
    store.update_node_status(root.id, NodeStatus.DONE)
    
    nxt2 = store.get_next_pending_node(chain.id)
    # Next highest priority 
    assert nxt2.id == child2.id
    
    # Test children order
    children = store.get_node_children(root.id)
    assert len(children) == 2
    assert children[0].id == child1.id  # planned_order 1
    assert children[1].id == child2.id  # planned_order 2

def test_context_building(setup_db):
    store = TreeStore(vector_store=DummyVectorStore())
    chain = store.create_chain(session_id="test_sess_ctx")
    
    root = store.add_node(Node(
        chain_id=chain.id,
        agent_role=AgentRole.ORCHESTRATOR,
        type=NodeType.PLAN,
        content="Root plan",
        priority=10
    ))
    
    child = store.add_node(Node(
        chain_id=chain.id,
        parent_id=root.id,
        agent_role=AgentRole.TOOLS,
        type=NodeType.RESULT,
        content="Result of data",
        priority=5
    ))
    
    ctx = store.build_context(chain.id, "query doesn't matter much", current_node_id=child.id)
    
    assert len(ctx) >= 2
    assert "score" in ctx[0]
