import asyncio
import time
from typing import List, Dict, Optional
from agent_core.llm.models import LLMRequest, Priority

class BatchManager:
    """
    Manages micro-batching of LLM requests with priority support.
    Groups requests by model and parameters, then flushes them based on
    a sliding window (batch_interval) or when max_batch_size is reached.
    """
    def __init__(self, batch_interval_ms: int = 50, max_batch_size: int = 8):
        self.batch_interval = batch_interval_ms / 1000.0
        self.max_batch_size = max_batch_size
        
        # Key: model_tokens_temp, Value: List of LLMRequest (sorted by priority)
        self._groups: Dict[str, List[LLMRequest]] = {}
        # Key: group_key, Value: monotonic time when the batch must be flushed
        self._deadlines: Dict[str, float] = {}
        
        self._lock = asyncio.Lock()
        self._new_data_event = asyncio.Event()

    async def add_request(self, req: LLMRequest):
        """Add a request to the appropriate batch group."""
        group_key = self._get_group_key(req)
        
        async with self._lock:
            if group_key not in self._groups:
                self._groups[group_key] = []
                # First request in group sets the deadline for the window
                self._deadlines[group_key] = time.monotonic() + self.batch_interval
            
            # Maintain priority order within the group (Lower value = Higher priority)
            inserted = False
            for i, existing in enumerate(self._groups[group_key]):
                if req.priority < existing.priority:
                    self._groups[group_key].insert(i, req)
                    inserted = True
                    break
            if not inserted:
                self._groups[group_key].append(req)
                
            self._new_data_event.set()

    def _get_group_key(self, req: LLMRequest) -> str:
        return f"{req.model}_{req.max_tokens}_{req.temperature}"

    async def wait_for_data(self, timeout: float = 1.0):
        """Wait for new data or until a timeout occurs."""
        try:
            await asyncio.wait_for(self._new_data_event.wait(), timeout=timeout)
            self._new_data_event.clear()
        except asyncio.TimeoutError:
            pass

    async def get_batches_to_flush(self) -> List[List[LLMRequest]]:
        """
        Check all groups and return batches that are ready to be processed.
        A batch is ready if it's full or the deadline has passed.
        """
        now = time.monotonic()
        batches = []
        
        async with self._lock:
            for key in list(self._groups.keys()):
                group = self._groups[key]
                deadline = self._deadlines[key]
                
                # If batch is full or deadline passed, extract a batch
                while len(group) >= self.max_batch_size or (group and now >= deadline):
                    count = min(len(group), self.max_batch_size)
                    batch = group[:count]
                    batches.append(batch)
                    
                    # Update the remaining group
                    group = group[count:]
                    self._groups[key] = group
                    
                    # If there's still data, reset the deadline for the next batch
                    if group:
                        self._deadlines[key] = now + self.batch_interval
                    else:
                        # Clean up empty group
                        del self._groups[key]
                        del self._deadlines[key]
                        break
        
        return batches

    async def clear_all(self):
        """Clear all pending requests."""
        async with self._lock:
            self._groups.clear()
            self._deadlines.clear()
            self._new_data_event.clear()
