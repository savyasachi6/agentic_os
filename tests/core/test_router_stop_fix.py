import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from core.llm.router import LLMRouter
from core.llm.models import Priority

@pytest.mark.asyncio
async def test_router_stop_propagation():
    """
    Verify that the 'stop' parameter is correctly passed through the router to the backend.
    """
    # Fresh router instance
    router = LLMRouter(batch_interval_ms=50, max_batch_size=5)
    
    mock_backend = AsyncMock()
    # Capture the stop parameter
    captured_stop = []
    
    async def mock_generate_batch(messages_batch, model, max_tokens, temperature, stop=None):
        captured_stop.append(stop)
        return ["Response" for _ in range(len(messages_batch))]
        
    mock_backend.generate_batch.side_effect = mock_generate_batch
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # Call submit with a stop sequence
        stop_seq = ["Observation:"]
        result = await router.submit(
            messages=[{"role": "user", "content": "Hello"}],
            session_id="test_session",
            model="test_model",
            stop=stop_seq
        )
        
        router.stop()
        
        assert result == "Response"
        # Verify that the backend received the correct stop parameter
        assert len(captured_stop) == 1
        assert captured_stop[0] == stop_seq

@pytest.mark.asyncio
async def test_router_grouping_by_stop():
    """
    Verify that requests with different stop sequences are NOT batched together.
    """
    router = LLMRouter(batch_interval_ms=50, max_batch_size=5)
    
    mock_backend = AsyncMock()
    mock_backend.generate_batch.return_value = ["Resp"]
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # Submit 2 requests with DIFFERENT stop sequences
        f1 = router.submit([{"content": "R1"}], "s1", "m", stop=["StopA"])
        f2 = router.submit([{"content": "R2"}], "s2", "m", stop=["StopB"])
        
        await asyncio.gather(f1, f2)
        router.stop()
        
        # Should result in 2 backend calls because the grouping key (which includes stop) differs
        assert mock_backend.generate_batch.call_count == 2
