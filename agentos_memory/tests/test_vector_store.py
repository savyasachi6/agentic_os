import pytest
from unittest.mock import MagicMock, patch

# Global mocks for config
mock_db_settings = MagicMock()
mock_model_settings = MagicMock()
mock_model_settings.embed_model = "test-model"

def get_vector_store():
    with patch.dict("sys.modules", {"config": MagicMock(db_settings=mock_db_settings, model_settings=mock_model_settings)}):
        from agent_memory.vector_store import VectorStore
        return VectorStore()

@pytest.fixture
def mock_ollama():
    with patch("agent_memory.vector_store.ollama") as mock:
        mock.embeddings.return_value = {"embedding": [0.1, 0.2, 0.3]}
        yield mock

@pytest.fixture
def mock_db_conn():
    with patch("agent_memory.vector_store.get_db_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_conn.return_value = mock_conn
        yield mock_cur

class TestVectorStore:
    def test_generate_embedding(self, mock_ollama):
        vs = get_vector_store()
        vs.embed_model = "test-model"
        emb = vs.generate_embedding("hello world")
        assert emb == [0.1, 0.2, 0.3]
        mock_ollama.embeddings.assert_called_once_with(model="test-model", prompt="hello world")

    def test_log_thought(self, mock_ollama, mock_db_conn):
        vs = get_vector_store()
        vs.log_thought(session_id="sess-123", role="user", content="thinking...")
        
        # Verify SQL call
        args, kwargs = mock_db_conn.execute.call_args
        sql = args[0]
        params = args[1]
        
        assert "INSERT INTO thoughts" in sql
        assert params[0] == "sess-123"
        assert params[1] == "user"
        assert params[2] == "thinking..."
        assert params[3] == [0.1, 0.2, 0.3]

    def test_search_thoughts(self, mock_ollama, mock_db_conn):
        vs = get_vector_store()
        mock_db_conn.fetchall.return_value = [
            ("sess-123", "user", "thought 1", 0.95),
            ("sess-123", "assistant", "thought 2", 0.85)
        ]
        
        results = vs.search_thoughts(query="test query", session_id="sess-123", limit=2)
        
        assert len(results) == 2
        assert results[1]["content"] == "thought 2"
        assert results[1]["score"] == 0.85
        
        # Verify SQL filtering by session_id
        args, _ = mock_db_conn.execute.call_args
        sql = args[0]
        assert "WHERE session_id = %s" in sql
        assert "embedding <=> %s::vector" in sql

    def test_upsert_skill(self, mock_db_conn):
        vs = get_vector_store()
        mock_db_conn.fetchone.return_value = [42]
        
        skill_id = vs.upsert_skill(
            name="test-skill", 
            description="desc", 
            tags=["tag1"], 
            path="/path", 
            eval_lift=1.5
        )
        
        assert skill_id == 42
        args, _ = mock_db_conn.execute.call_args
        assert "INSERT INTO knowledge_skills" in args[0]
        assert "ON CONFLICT (normalized_name) DO UPDATE" in args[0]
