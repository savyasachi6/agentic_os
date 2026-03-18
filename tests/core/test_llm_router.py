import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from llm_router.router import LLMRouter
from llm_router.models import LLMRequest

def test_llm_router_singleton():
    """Verify that get_instance returns a singleton."""
    r1 = LLMRouter.get_instance()
    r2 = LLMRouter.get_instance()
    assert r1 is r2

@pytest.mark.asyncio
async def test_llm_router_true_batching():
    """
    Test that multiple concurrent submit() calls are grouped into exactly ONE batch call.
    """
    # Use a fresh instance for testing to avoid singleton contamination
    router = LLMRouter(batch_interval_ms=50, max_batch_size=5)
    
    # Mock the backend generate_batch method
    mock_backend = AsyncMock()
    mock_backend.generate_batch.side_effect = lambda messages_batch, **kwargs: [f"Resp {i}" for i in range(len(messages_batch))]
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # Submit 3 requests concurrently
        t1 = router.submit([{"role": "user", "content": "Req 1"}], session_id="s1", model="m1")
        t2 = router.submit([{"role": "user", "content": "Req 2"}], session_id="s2", model="m1")
        t3 = router.submit([{"role": "user", "content": "Req 3"}], session_id="s3", model="m1")
        
        results = await asyncio.gather(t1, t2, t3)
        router.stop()
        
        assert results == ["Resp 0", "Resp 1", "Resp 2"]
        # CRITICAL: Verify only ONE backend call was made for all 3 requests
        assert mock_backend.generate_batch.call_count == 1

@pytest.mark.asyncio
async def test_llm_router_batch_error_propagation():
    """Verify that if the batch call fails, the error propagates to all futures."""
    router = LLMRouter(batch_interval_ms=50)
    
    mock_backend = AsyncMock()
    mock_backend.generate_batch.side_effect = Exception("GPU OOM")
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        t1 = router.submit([{"role": "user", "content": "Req 1"}], session_id="s1", model="m1")
        t2 = router.submit([{"role": "user", "content": "Req 2"}], session_id="s2", model="m1")
        
        with pytest.raises(RuntimeError, match="GPU OOM"):
            await asyncio.gather(t1, t2)
        
        router.stop()

@pytest.mark.asyncio
async def test_llm_router_multiplexing():
    """Verify that different models/params result in different batch groups."""
    router = LLMRouter(batch_interval_ms=50, max_batch_size=10)
    
    mock_backend = AsyncMock()
    mock_backend.generate_batch.return_value = ["Resp"]
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # Two different models
        t1 = router.submit([{"role": "user", "content": "M1"}], session_id="s1", model="model-a")
        t2 = router.submit([{"role": "user", "content": "M2"}], session_id="s2", model="model-b")
        
        await asyncio.gather(t1, t2)
        router.stop()
        
        # Should be 2 calls because model names differ
        assert mock_backend.generate_batch.call_count == 2
