import asyncio
import logging
import httpx
from typing import List, Dict
from llm_router.backends.base import LLMBackend
from agent_core.resilience import async_retry, RETRYABLE_EXCEPTIONS

logger = logging.getLogger("agentos.ollama_backend")

# Keep a single shared AsyncClient across all calls so TCP connections are
# reused (keep-alive). This is exactly what Ollama's own Go client does.
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
    ) -> List[str]:
        """
        Fire concurrent async requests to Ollama with per-request retry/backoff.
        Uses a persistent keep-alive AsyncClient so TCP connections survive
        brief network blips — the same technique used by Ollama and Open WebUI.
        """
        client = _get_client()

        @async_retry(max_attempts=5, base_delay=1.0, cap_delay=30.0, label="OllamaBackend.fetch")
        async def fetch(messages: List[Dict[str, str]]) -> str:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("[OllamaBackend] Batch item failed after all retries: %s", r)
                processed.append(f"[Error: {r}]")
            else:
                processed.append(str(r))
        return processed
