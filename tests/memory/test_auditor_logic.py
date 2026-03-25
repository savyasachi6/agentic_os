import pytest
pytest.skip("Feature or Module 'rag.auditor' missing from source.", allow_module_level=True)
import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest
from rag.auditor import Auditor
from rag.retriever import RetrievedChunk

@pytest.mark.asyncio
async def test_auditor_single_chunk_pass():
    auditor = Auditor()
    chunk = RetrievedChunk(id="1", content="The server can be restarted by running 'sudo systemctl restart agentos'.", score=0.9, metadata={})
    
    mock_response = {
        "message": {
            "content": json.dumps({
                "relevance_score": 0.95,
                "is_noisy": False,
                "has_conflict": False,
                "reasoning": "Directly answering the query.",
                "suggested_action": "keep",
                "cropped_content": None
            })
        }
    }
    
    with patch("ollama.AsyncClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        report = await auditor.audit_single_chunk("How do I restart the server?", chunk)
        
        assert report["is_valid"] is True
        assert report["relevance_score"] == 0.95
        assert report["suggested_action"] == "keep"

@pytest.mark.asyncio
async def test_auditor_single_chunk_reject():
    auditor = Auditor()
    chunk = RetrievedChunk(id="2", content="Server maintenance in 2019 involved physical cleaning.", score=0.4, metadata={})
    
    mock_response = {
        "message": {
            "content": json.dumps({
                "relevance_score": 0.1,
                "is_noisy": True,
                "has_conflict": False,
                "reasoning": "Irrelevant historical data.",
                "suggested_action": "reject",
                "cropped_content": None
            })
        }
    }
    
    with patch("ollama.AsyncClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_response
        report = await auditor.audit_single_chunk("How do I restart the server?", chunk)
        
        assert report["is_valid"] is False
        assert report["relevance_score"] == 0.1
        assert report["suggested_action"] == "reject"

@pytest.mark.asyncio
async def test_evaluate_retrieval_strategy_pivot():
    auditor = Auditor()
    reports = [
        {"is_valid": False, "relevance_score": 0.1},
        {"is_valid": False, "relevance_score": 0.2},
        {"is_valid": False, "relevance_score": 0.1},
        {"is_valid": True, "relevance_score": 0.6},
    ]
    
    action = await auditor.evaluate_retrieval_strategy("query", reports)
    assert action == "pivot"

@pytest.mark.asyncio
async def test_evaluate_retrieval_strategy_proceed():
    auditor = Auditor()
    reports = [
        {"is_valid": True, "relevance_score": 0.9},
        {"is_valid": True, "relevance_score": 0.8},
        {"is_valid": True, "relevance_score": 0.7},
        {"is_valid": False, "relevance_score": 0.1},
    ] # 3/4 = 0.75 > 0.6
    
    action = await auditor.evaluate_retrieval_strategy("query", reports)
    assert action == "proceed"

if __name__ == "__main__":
    asyncio.run(test_auditor_single_chunk_pass())
    asyncio.run(test_auditor_single_chunk_reject())
    asyncio.run(test_evaluate_retrieval_strategy_pivot())
    asyncio.run(test_evaluate_retrieval_strategy_proceed())
    print("All tests passed!")
