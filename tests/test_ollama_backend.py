import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from llm_router.backends.ollama_api import OllamaBackend

@pytest.mark.asyncio
async def test_ollama_backend_generate_batch():
    # Setup backend
    backend = OllamaBackend(base_url="http://mock-ollama:11434")
    
    messages_batch = [[{"role": "user", "content": "Hello"}]]
    model = "llama3"
    max_tokens = 100
    temperature = 0.5
    stop = ["STOP"]
    
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": "Mocked response"}}
    mock_response.raise_for_status = MagicMock()
    
    # Patch the shared client's post method
    # We need to patch the _get_client function in the module
    with patch("llm_router.backends.ollama_api._get_client") as mock_get_client:
        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_get_client.return_value = mock_http_client
        
        results = await backend.generate_batch(
            messages_batch=messages_batch,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop
        )
        
        # Verify results
        assert len(results) == 1
        assert results[0] == "Mocked response"
        
        # Verify call details
        mock_http_client.post.assert_called_once()
        args, kwargs = mock_http_client.post.call_args
        
        assert args[0] == "http://mock-ollama:11434/api/chat"
        payload = kwargs["json"]
        assert payload["model"] == model
        assert payload["messages"] == messages_batch[0]
        assert payload["options"]["temperature"] == temperature
        assert payload["options"]["num_predict"] == max_tokens
        assert payload["options"]["stop"] == stop
        assert kwargs["timeout"] == 120.0

if __name__ == "__main__":
    asyncio.run(test_ollama_backend_generate_batch())
