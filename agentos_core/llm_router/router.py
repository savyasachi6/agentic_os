import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional

from config import llm_router_settings
from llm_router.backends import LLMBackend, OllamaBackend, LlamaCPPBackend

from .models import LLMRequest, LLMResponse, BatchGroup

class LLMRouter:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._batch_interval = llm_router_settings.batch_interval_ms / 1000.0
        self._max_batch_size = llm_router_settings.max_batch_size
        
        # Determine backend based on configuration
        backend_type = getattr(llm_router_settings, "backend", "ollama")
        if backend_type == "llama-cpp":
            print(f"[LLMRouter] Configuring Native Llama-CPP backend with {getattr(llm_router_settings, 'llama_cpp_model_path', 'models/qwen3-vl-8b.gguf')}")
            self.backend: LLMBackend = LlamaCPPBackend(
                model_path=getattr(llm_router_settings, "llama_cpp_model_path", "models/qwen3-vl-8b.gguf")
            )
        else:
            print(f"[LLMRouter] Configuring HTTP API Ollama backend at {getattr(llm_router_settings, 'ollama_base_url', 'http://localhost:11434')}")
            self.backend: LLMBackend = OllamaBackend(
                base_url=getattr(llm_router_settings, "ollama_base_url", "http://localhost:11434")
            )
        self.queue: asyncio.Queue[LLMRequest] = asyncio.Queue()
        self.pending_futures: Dict[str, asyncio.Future] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def start(self):
        """Start the background routing task."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._batch_loop())
            print(f"[LLMRouter] Started with batch_interval={self._batch_interval * 1000.0}ms, max_batch={self._max_batch_size}")

    def stop(self):
        """Stop the background routing task."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            self._task = None
            print("[LLMRouter] Stopped")

    async def submit(self, messages: List[Dict[str, str]], session_id: str, model: str, max_tokens: int = 2048, temperature: float = 0.7) -> str:
        """
        Submit a new generation request to the router.
        Returns the generated content string asynchronously.
        """
        request_id = str(uuid.uuid4())
        req = LLMRequest(
            request_id=request_id,
            session_id=session_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_futures[request_id] = future
        
        await self.queue.put(req)
        
        # Wait for the background loop to process and set the result
        response: LLMResponse = await future
        if response.error:
            raise RuntimeError(response.error)
        return response.content

    async def _batch_loop(self):
        """Background loop reading from the queue and grouping requests into batches."""
        while not self._stop_event.is_set():
            batch = []
            
            try:
                # Wait for at least one item
                req = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                batch.append(req)
                
                # Try to gather more items within the batch interval
                deadline = time.monotonic() + self._batch_interval
                while len(batch) < self._max_batch_size:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        break
                    try:
                        next_req = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                        batch.append(next_req)
                    except asyncio.TimeoutError:
                        break
                        
            except asyncio.TimeoutError:
                continue # loop again
            except asyncio.CancelledError:
                break
                
            if batch:
                asyncio.create_task(self._process_batch(batch))
                for _ in batch:
                    self.queue.task_done()

    async def _process_batch(self, batch: List[LLMRequest]):
        """Group requests by model/params and dispatch to backend, then demux results."""
        # Simple grouping by model and max_tokens
        groups: Dict[str, BatchGroup] = {}
        for req in batch:
            key = f"{req.model}_{req.max_tokens}_{req.temperature}"
            if key not in groups:
                groups[key] = BatchGroup(model=req.model, max_tokens=req.max_tokens)
            groups[key].requests.append(req)
            
        for key, group in groups.items():
            messages_batch = [req.messages for req in group.requests]
            
            try:
                # Send to backend
                # Currently taking the temperature from the first request in group as representative
                temp = group.requests[0].temperature if group.requests else 0.7
                
                results = await self.backend.generate_batch(
                    messages_batch=messages_batch, 
                    model=group.model, 
                    max_tokens=group.max_tokens,
                    temperature=temp
                )
                
                # Demux and resolve futures
                for idx, req in enumerate(group.requests):
                    content = results[idx] if idx < len(results) else ""
                    self._resolve_future(req.request_id, req.session_id, content)
                    
            except Exception as e:
                print(f"[LLMRouter] Error processing batch: {e}")
                for req in group.requests:
                    self._resolve_future(req.request_id, req.session_id, "", error=str(e))

    def _resolve_future(self, request_id: str, session_id: str, content: str, error: Optional[str] = None):
        if request_id in self.pending_futures:
            future = self.pending_futures.pop(request_id)
            if not future.done():
                resp = LLMResponse(request_id=request_id, session_id=session_id, content=content, error=error)
                future.set_result(resp)
