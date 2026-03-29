import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Mock problematic modules before any other imports to avoid ModuleNotFoundError
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()
sys.modules["mcp"] = MagicMock()
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.pool"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()
sys.modules["db.connection"] = MagicMock()
# Mock the entire agent_core and rag to avoid deep dependency issues
sys.modules["core.settings"] = MagicMock()
sys.modules["agent_core.utils.auth"] = MagicMock()
sys.modules["llm_router.router"] = MagicMock()
# Mock the specific KeycloakManager if needed by server.py at import time
mock_auth = MagicMock()
sys.modules["agent_core.utils.auth"].KeycloakManager = mock_auth

import pytest
from fastapi.testclient import TestClient

# Decorator to bypass Keycloak dependency in FastAPI
def mock_verify_token():
    return {"user_id": "test_user", "roles": ["admin"]}

with patch("llm_router.router.LLMRouter.get_instance") as mock_router:
    mock_router.return_value = MagicMock()
    from gateway.server import app
    # Override the dependency for any endpoint that might use it
    from agent_core.utils.auth import KeycloakManager
    app.dependency_overrides[KeycloakManager.verify_token] = mock_verify_token

client = TestClient(app)

@pytest.mark.asyncio
async def test_human_feedback_composition():
    """Test that the gateway correctly calls the RL Router with provided metrics."""
    
    # Payload from UI
    payload = {
        "chain_id": 123,
        "arm": 2,
        "feedback": 1,
        "query_hash_rl": "abc123query",
        "depth": 1,
        "step_count": 3,
        "invalid_call_count": 0
    }
    
    # Mock the RLRoutingClient submit_feedback
    with patch("rag.retrieval.rl_client.RLRoutingClient.submit_feedback", new_callable=AsyncMock) as mock_submit:
        mock_submit.return_value = {"status": "success", "reward_scalar": 0.85}
        
        response = client.post("/api/feedback/human", json=payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify it passed the correct values to the router client
        mock_submit.assert_called_once_with(
            query_hash="abc123query",
            arm_index=2,
            success=True,
            step_count=3,
            invalid_call_count=0,
            user_feedback=1.0,
            depth_used=1
        )

@pytest.mark.asyncio
async def test_human_feedback_metrics_lookup():
    """Test that the gateway falls back to session metrics if not provided by UI."""
    
    # Payload from UI (missing metrics part)
    payload = {
        "chain_id": 123,
        "arm": 2,
        "feedback": -1,
        "query_hash_rl": "abc123query",
        "depth": 1
    }
    
    # Mock an active session
    mock_agent = MagicMock()
    mock_agent.chain_id = 123
    mock_agent.last_run_metrics = {
        "step_count": 5,
        "invalid_call_count": 2
    }
    
    # We patch the internal _sessions dict in the server module
    with patch("gateway.server._sessions", { "test_session": mock_agent }):
        with patch("rag.retrieval.rl_client.RLRoutingClient.submit_feedback", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = {"status": "success"}
            
            response = client.post("/api/feedback/human", json=payload)
            
            assert response.status_code == 200
            
            # Verify lookup matched the session metrics
            mock_submit.assert_called_once_with(
                query_hash="abc123query",
                arm_index=2,
                success=True,
                step_count=5,
                invalid_call_count=2,
                user_feedback=-1.0,
                depth_used=1
            )
