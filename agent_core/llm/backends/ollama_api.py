import asyncio
import logging
import json
import httpx
from typing import List, Dict, Optional

from .base import LLMBackend
from agent_core.resilience import async_retry, RETRYABLE_EXCEPTIONS

logger = logging.getLogger("agentos.ollama_backend")

_SHARED_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _SHARED_CLIENT


class OllamaBackend(LLMBackend):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def validate_models(self, models: List[str]):
        """Check if all required models are pulled (Phase 83 Hardening)."""
        http_client = _get_client()
        try:
            resp = await http_client.get(f"{self.base_url}/api/tags", timeout=10.0)
            if resp.status_code == 200:
                available = [m["name"] for m in resp.json().get("models", [])]
                for model in models:
                    if model not in available:
                        logger.warning(f"[OllamaBackend] Model '{model}' is NOT pulled. Hybrid search or generation will fail.")
        except Exception as e:
            logger.error(f"[OllamaBackend] Could not validate models: {e}")

    async def generate_batch(
        self,
        messages_batch: List[List[Dict[str, str]]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Fire concurrent async requests using the shared httpx pool directly.
        No ollama SDK used here — avoids the BaseClient.init() conflict entirely.
        """
        http_client = _get_client()

        @async_retry(
            max_attempts=5, 
            base_delay=2.0, 
            cap_delay=60.0, 
            label="OllamaBackend.fetch",
            retryable_exceptions=(RETRYABLE_EXCEPTIONS + (ValueError,))
        )
        async def fetch(messages: List[Dict[str, str]]) -> str:
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,  # Streaming to keep connection alive during long think chains
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": 16384,
                    "stop": stop,
                },
            }
            try:
                async with http_client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=httpx.Timeout(300.0, read=None)
                ) as resp:
                    resp.raise_for_status()
                    
                    full_content = []
                    full_thinking = []
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk_data = json.loads(line)
                        msg = chunk_data.get("message", {})
                        
                        # Collect content tokens (final answer)
                        token = msg.get("content", "")
                        if token:
                            full_content.append(token)
                        
                        # Collect thinking tokens (internal monologue for qwen3-style models)
                        thinking_token = msg.get("thinking", "")
                        if thinking_token:
                            full_thinking.append(thinking_token)
                        
                        if chunk_data.get("done"):
                            break
                    
                    content = "".join(full_content)
                    thinking = "".join(full_thinking)
                    
                    if (not content or content.strip() == "") and (not thinking or thinking.strip() == ""):
                        logger.warning("[OllamaBackend] Stream finished with zero content and zero thinking tokens. Retrying.")
                        raise ValueError("Ollama returned completely empty response content.")
                    
                    # Prepend thinking trace if available (qwen3-vl:8b style thinking models)
                    # Format: <|thinking|>...thinking...<|/thinking|>\n<|content|>...content...
                    # Specialists can extract this to show real model reasoning in the UI.
                    if thinking.strip():
                        full_result = f"<|thinking|>{thinking}<|/thinking|>\n{content}"
                    else:
                        full_result = content
                    
                    logger.debug("[OllamaBackend] Stream consumed. content_len=%d, think_len=%d", len(content), len(thinking))
                    return full_result
            except Exception as e:
                logger.error("[OllamaBackend] Fetch error during stream: %s", e)
                raise

        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("[OllamaBackend] Batch item failed: %s", r)
                raise r  # Propagate the error instead of swallowing it as a string
            else:
                processed.append(str(r))
        return processed
