import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
from core.llm.router import LLMRouter
from core.llm.models import Priority, LLMRequest

@pytest.mark.asyncio
async def test_priority_batching_order():
    """
    Test that high-priority (OBSERVER) requests jump to the front of the batch
    even if they arrive after low-priority (SUMMARIZATION) requests.
    """
    # Small batch size to trigger flush easily
    router = LLMRouter(batch_interval_ms=100, max_batch_size=5)
    
    mock_backend = AsyncMock()
    # Capture the batched messages to check order
    captured_batches = []
    
    async def mock_generate_batch(messages_batch, **kwargs):
        captured_batches.append(messages_batch)
        return [f"Resp {i}" for i in range(len(messages_batch))]
        
    mock_backend.generate_batch.side_effect = mock_generate_batch
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # 1. Submit 4 LOW priority requests (Summarization)
        futures = []
        for i in range(4):
            futures.append(router.submit(
                [{"role": "user", "content": f"Low {i}"}], 
                session_id="s1", 
                model="m1", 
                priority=Priority.SUMMARIZATION
            ))
            
        # Small sleep to ensure they are queued
        await asyncio.sleep(0.01)
        
        # 2. Submit 1 HIGH priority request (Observer)
        # Total requests = 5 (matches max_batch_size)
        futures.append(router.submit(
            [{"role": "user", "content": "High Priority"}], 
            session_id="s1", 
            model="m1", 
            priority=Priority.OBSERVER
        ))
        
        results = await asyncio.gather(*futures)
        router.stop()
        
        # Check results count
        assert len(results) == 5
        
        # Check backend calls
        assert len(captured_batches) == 1
        batch_messages = captured_batches[0]
        assert len(batch_messages) == 5
        
        # The HIGH priority request should be at the FRONT (index 0)
        # despite being submitted last.
        assert batch_messages[0][0]["content"] == "High Priority"
        # The LOW priority requests follow
        assert batch_messages[1][0]["content"] == "Low 0"

@pytest.mark.asyncio
async def test_priority_jumping_to_next_batch():
    """
    If a batch is full, high priority should still be at the front of the NEXT batch.
    Or if it arrives in time, it should kick out a low-priority from a full batch.
    """
    router = LLMRouter(batch_interval_ms=100, max_batch_size=2)
    mock_backend = AsyncMock()
    captured_batches = []
    mock_backend.generate_batch.side_effect = lambda messages_batch, **kwargs: (captured_batches.append(messages_batch), [f"R" for _ in range(len(messages_batch))])[1]
    
    with patch.object(router, 'backend', mock_backend):
        router.start()
        
        # Send 2 Normal
        f1 = router.submit([{"content": "N1"}], "s", "m")
        f2 = router.submit([{"content": "N2"}], "s", "m")
        
        # Send 1 High
        f3 = router.submit([{"content": "H1"}], "s", "m", priority=Priority.OBSERVER)
        
        await asyncio.gather(f1, f2, f3)
        router.stop()
        
        # Order in groups: [H1, N1, N2]
        # Batch 1 (size 2): [H1, N1]
        # Batch 2 (size 1): [N2]
        assert captured_batches[0][0][0]["content"] == "H1"
        assert captured_batches[1][0][0]["content"] == "N2"
