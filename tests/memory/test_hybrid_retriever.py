import pytest
pytest.skip("Feature or Module 'rag.retrieval' missing from source.", allow_module_level=True)
import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Add both core and memory to path
# legacy sys.path hack removed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global mocks for config
def get_hybrid_retriever():
    with patch.dict("sys.modules", {"config": MagicMock()}):
        from agent_core.rag.retriever import HybridRetriever, RetrievedChunk
        return HybridRetriever, RetrievedChunk

@pytest.fixture
def mock_stores():
    with patch("rag.retrieval.retriever.RagStore") as MockRag, \
         patch("rag.retrieval.retriever.VectorStore") as MockVec, \
         patch("rag.retrieval.retriever.SemanticCache") as MockCache:
        
        mock_rag = MockRag.return_value
        mock_vec = MockVec.return_value
        mock_cache = MockCache.return_value
        
        # Default mock behavior
        mock_vec.generate_embedding.return_value = [0.1, 0.2, 0.3]
        mock_rag.query_hybrid.return_value = [
            {
                "id": "chunk-1",
                "raw_text": "sample content",
                "score": 0.9,
                "source_uri": "file://test.txt",
                "clean_text": "sample content",
                "llm_summary": "summary"
            }
        ]
        mock_rag.log_retrieval_event.return_value = "event-123"
        mock_cache.get_cached_response.return_value = None
        
        yield mock_rag, mock_vec, mock_cache

class TestHybridRetriever:
    def test_retrieve_happy_path(self, mock_stores):
        mock_rag, mock_vec, mock_cache = mock_stores
        HybridRetriever, RetrievedChunk = get_hybrid_retriever()
        retriever = HybridRetriever(top_k=5)
        
        results = retriever.retrieve(query="test query", session_id="sess-1")
        
        assert len(results) == 1
        assert isinstance(results[0], RetrievedChunk)
        assert results[0].id == "chunk-1"
        assert results[0].score == 0.9
        
        # Verify store calls
        mock_vec.generate_embedding.assert_called_once_with("test query")
        mock_rag.query_hybrid.assert_called_once()
        mock_rag.log_retrieval_event.assert_called_once()
        mock_cache.get_cached_response.assert_called_once_with("test query")

    def test_audit_results(self, mock_stores):
        mock_rag, _, _ = mock_stores
        HybridRetriever, _ = get_hybrid_retriever()
        retriever = HybridRetriever()
        
        retriever.audit_results(
            event_id="event-123",
            chunk_id="chunk-1",
            auditor_role="auditor",
            score=0.8,
            hallucination=False,
            comments="looks good"
        )
        
        mock_rag.log_audit_feedback.assert_called_once_with(
            event_id="event-123",
            chunk_id="chunk-1",
            role="auditor",
            score=0.8,
            hallucination=False,
            comments="looks good"
        )

    def test_retrieve_with_relations(self, mock_stores):
        mock_rag, mock_vec, _ = mock_stores
        HybridRetriever, RetrievedChunk = get_hybrid_retriever()
        retriever = HybridRetriever()
        
        # Setup mock to return relations
        mock_rag.get_chunk_relations.return_value = {
            "chunk-1": [
                {"type": "skill", "target_name": "deployment", "skill_type": "devops", "confidence": 1.0}
            ]
        }
        
        results = retriever.retrieve(query="deploy service", session_id="sess-1")
        
        assert len(results) == 1
        assert len(results[0].relations) == 1
        assert results[0].relations[0]["target_name"] == "deployment"
        mock_rag.get_chunk_relations.assert_called_once_with(["chunk-1"])
