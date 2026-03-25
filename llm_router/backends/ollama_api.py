import asyncio
import logging
import httpx
from typing import List, Dict, Optional

from llm_router.backends.base import LLMBackend
from agent_core.resilience import async_retry, RETRYABLE_EXCEPTIONS

logger = logging.getLogger("agentos.ollama_backend")

_SHARED_CLIENT: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _SHARED_CLIENT


class OllamaBackend(LLMBackend):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

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

        @async_retry(max_attempts=5, base_delay=1.0, cap_delay=30.0, label="OllamaBackend.fetch")
        async def fetch(messages: List[Dict[str, str]]) -> str:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": 8192,
                    "stop": stop,
                },
            }
            try:
                resp = await http_client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=120.0,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                logger.debug("[OllamaBackend] Response len: %d", len(content))
                return content
            except Exception as e:
                logger.error("[OllamaBackend] Fetch error: %s", e)
                raise

        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("[OllamaBackend] Batch item failed: %s", r)
                processed.append(f"[Error: {r}]")
            else:
                processed.append(str(r))
        return processed
