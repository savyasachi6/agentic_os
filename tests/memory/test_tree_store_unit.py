import sys
from unittest.mock import MagicMock

# Mock 'config' module before importing memory components
mock_config = MagicMock()
mock_config.db_settings.min_connections = 1
mock_config.db_settings.max_connections = 10
sys.modules["config"] = mock_config

import pytest
from unittest.mock import patch
from datetime import datetime

from db.queries.commands import TreeStore
from db.models import Chain, Node, AgentRole, NodeType, NodeStatus

@pytest.fixture
def mock_db():
    with patch("agent_memory.tree_store.get_db_connection") as mock:
        yield mock

@pytest.fixture
def mock_vector_store():
    mock = MagicMock()
    mock.generate_embedding.return_value = ([0.1] * 1024, False)
    return mock

@pytest.fixture
def tree_store(mock_vector_store):
    return TreeStore(vector_store=mock_vector_store)

def test_create_chain(tree_store, mock_db):
    mock_conn = mock_db.return_value.__enter__.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    mock_cur.fetchone.return_value = (1, datetime.now())

    chain = tree_store.create_chain("session-123", "Test Chain")

    assert chain.id == 1
    assert chain.session_id == "session-123"
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

def test_add_node(tree_store, mock_db):
    mock_conn = mock_db.return_value.__enter__.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    now = datetime.now()
    mock_cur.fetchone.return_value = (10, now, now)

    node = Node(
        chain_id=1,
        agent_role=AgentRole.RAG,
        type=NodeType.LLM_CALL,
        content="Testing node"
    )
    
    saved_node = tree_store.add_node(node)

    assert saved_node.id == 10
    assert saved_node.embedding == [0.1] * 1536
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

def test_get_next_pending_node(tree_store, mock_db):
    mock_conn = mock_db.return_value.__enter__.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    
    # Mock return row
    mock_cur.fetchone.return_value = (
        1, 1, None, "rag", "llm_call", "pending", 8,
        0, "content", "{}", None, [0.1]*1024, None, datetime.now(), datetime.now()
    )

    node = tree_store.get_next_pending_node(1)

    assert node.id == 1
    assert node.priority == 8
    assert node.status == NodeStatus.PENDING

def test_build_context_ranking(tree_store, mock_db):
    mock_conn = mock_db.return_value.__enter__.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    
    # return two nodes with different stats
    # nid, npid, nrole, ntype, nstatus, nprio, ncontent, sim, dfactor
    rows = [
        (1, None, "rag", "summary", "done", 10, "high priority", 0.5, 0.0), # score = 0.5*1.0 + 0.3*0.5 + 0.2*0 = 0.65
        (2, 1, "tools", "result", "done", 5, "low priority high sim", 0.9, 1.0), # score = 0.5*0.5 + 0.3*0.9 + 0.2*1.0 = 0.25+0.27+0.2 = 0.72
    ]
    mock_cur.fetchall.return_value = rows

    context, is_degraded = tree_store.build_context(1, "query", limit=5)

    assert len(context) == 2
    # Node 2 should be first because of higher depth factor and similarity
    assert context[0]["id"] == 2
    assert context[1]["id"] == 1
    assert context[0]["score"] > context[1]["score"]
