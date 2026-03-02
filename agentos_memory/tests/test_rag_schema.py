import pytest
import uuid
from unittest.mock import patch, MagicMock
from agent_memory.rag_store import RagStore

@pytest.fixture
def mock_db():
    with patch("agent_memory.rag_store.get_db_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        
        # Default fetchone return for inserts
        mock_cur.fetchone.return_value = [str(uuid.uuid4())]
        
        yield mock_cur

@pytest.fixture
def store():
    return RagStore()

def test_document_lifecycle(store, mock_db):
    uri = f"test://doc-{uuid.uuid4()}"
    doc_id = store.save_document(source_uri=uri, source_type="test", title="Test Document")
    assert doc_id is not None

def test_chunk_insertion_with_embedding(store, mock_db):
    uri = f"test://chunk-{uuid.uuid4()}"
    doc_id = store.save_document(source_uri=uri, source_type="test")
    
    chunks = [
        {
            "chunk_index": 0, 
            "raw_text": "This is a test chunk about machine learning.",
            "clean_text": "This is a test chunk about machine learning.",
            "embedding": [0.1] * 768,
            "metadata": {"section": "intro"}
        }
    ]
    
    store.upsert_chunks_with_embeddings(doc_id, chunks, "test-model")
    
    mock_db.fetchall.return_value = [
        (uuid.uuid4(), uuid.uuid4(), "machine learning test content", "clean", "summary", "uri", 0.9)
    ]
    
    # Verify via hybrid search
    results = store.query_hybrid(query_vector=[0.1]*768, query_text="machine learning", top_k=1)
    assert len(results) > 0
    assert "machine learning" in results[0]["raw_text"]

def test_skill_graph_traversal(store, mock_db):
    # 1. Create skills
    s1 = store.register_entity("Python", "language")
    s2 = store.register_entity("FastAPI", "framework")
    
    # 2. Add relation
    store.insert_entity_relation(s1, "entity", s2, "entity", "REQUIRES")
    
    # 3. Traverse
    mock_db.fetchall.return_value = [
        (1, "fastapi", "framework", "REQUIRES", 1.0, 1)
    ]
    results = store.traverse_graph(s1)
    assert any(r["name"] == "fastapi" for r in results) # Since normalized name is used

def test_audit_feedback_log(store, mock_db):
    event_id = store.log_retrieval_event(
        session_id="test-session",
        query="what is fastapi?",
        chunk_ids=[str(uuid.uuid4())],
        strategy="vector",
        latency_ms=10
    )
    assert event_id is not None
    
    store.log_audit_feedback(
        event_id=event_id,
        chunk_id=None,
        role="auditor",
        score=0.9,
        comments="Good retrieval"
    )
