import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock
from agent_core.llm.router import LLMRouter
from agent_core.llm.models import ModelTier, Priority
from agent_core.llm.backends import OpenAIBackend, OllamaBackend

@pytest.mark.asyncio
async def test_llm_router_failover_on_401():
    """
    Test that LLMRouter automatically falls back to Ollama when cloud (OpenAI) returns 401.
    """
    # Create a mock settings object
    mock_settings = MagicMock()
    mock_settings.router_backend = "openai"
    mock_settings.router_batch_size = 5
    mock_settings.ollama_model = "local-model"
    mock_settings.ollama_model_nano = "local-model-nano"
    mock_settings.ollama_model_fast = "local-model-fast"
    mock_settings.ollama_model_full = "local-model-full"
    mock_settings.ollama_base_url = "http://localhost:11434"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.openrouter_api_key = "fake-key"
    
    with patch("agent_core.llm.router.settings", mock_settings):
        router = LLMRouter(batch_interval_ms=10)
        
        # Mock Primary Backend (Cloud) - Must be an instance of OpenAIBackend
        cloud_mock = MagicMock(spec=OpenAIBackend)
        cloud_mock.generate_batch = AsyncMock(side_effect=Exception("401 Unauthorized: Invalid API Key"))
        
        # Mock Fallback Backend (Ollama)
        ollama_mock = MagicMock(spec=OllamaBackend)
        ollama_mock.generate_batch = AsyncMock(return_value=["Success from Ollama"])
        
        with patch.object(router, 'backend', cloud_mock):
            with patch.object(router, 'fallback_backend', ollama_mock):
                router.start()
                
                # Submit a request that would normally hit cloud
                result = await router.submit(
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="test_session",
                    tier=ModelTier.FULL
                )
                
                router.stop()
                
                # Assertions
                assert result == "Success from Ollama"
                assert cloud_mock.generate_batch.call_count == 1
                assert ollama_mock.generate_batch.call_count == 1
                
                # Verify circuit breaker is set (cooldown active)
                assert router._last_cloud_error_time > 0

@pytest.mark.asyncio
async def test_llm_router_circuit_breaker_active():
    """
    Test that LLMRouter skips cloud calls entirely while the circuit breaker is active.
    """
    mock_settings = MagicMock()
    mock_settings.router_backend = "openai"
    mock_settings.router_batch_size = 5
    mock_settings.ollama_model = "local-model"
    mock_settings.ollama_model_nano = "local-model-nano"
    mock_settings.ollama_model_fast = "local-model-fast"
    mock_settings.ollama_model_full = "local-model-full"
    
    with patch("agent_core.llm.router.settings", mock_settings):
        router = LLMRouter(batch_interval_ms=10)
        
        # Simulate a recent cloud error (current time)
        router._last_cloud_error_time = time.time()
        
        cloud_mock = MagicMock(spec=OpenAIBackend)  # is_cloud will be True
        cloud_mock.generate_batch = AsyncMock()
        
        ollama_mock = MagicMock(spec=OllamaBackend)
        ollama_mock.generate_batch = AsyncMock(return_value=["Skip Cloud Success"])
        
        with patch.object(router, 'backend', cloud_mock):
            with patch.object(router, 'fallback_backend', ollama_mock):
                router.start()
                
                result = await router.submit(
                    messages=[{"role": "user", "content": "hello again"}],
                    session_id="test_session_2"
                )
                
                router.stop()
                
                # Assertions
                assert result == "Skip Cloud Success"
                assert cloud_mock.generate_batch.call_count == 0  # Should NOT be called
                assert ollama_mock.generate_batch.call_count == 1
