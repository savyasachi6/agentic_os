import asyncio
import logging
import json
import httpx
from typing import List, Dict, Optional

from .base import LLMBackend
from agent_core.resilience import async_retry, RETRYABLE_EXCEPTIONS

logger = logging.getLogger("agentos.openai_backend")

_SHARED_CLIENT: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _SHARED_CLIENT


class OpenAIBackend(LLMBackend):
    """
    Backend for OpenAI-compatible APIs, including OpenRouter.
    Supports concurrent batching and thinking token capture for reasoning models.
    """
    def __init__(self, base_url: str = "https://api.openai.com/v1", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def generate_batch(
        self,
        messages_batch: List[List[Dict[str, str]]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Generates responses for a batch of requests concurrently.
        """
        http_client = _get_client()

        @async_retry(
            max_attempts=3, 
            base_delay=2.0, 
            cap_delay=30.0, 
            label="OpenAIBackend.fetch",
            retryable_exceptions=RETRYABLE_EXCEPTIONS
        )
        async def fetch(messages: List[Dict[str, str]]) -> str:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # OpenRouter specific headers for better discoverability and priority
            if "openrouter.ai" in self.base_url:
                headers.update({
                    "HTTP-Referer": "https://github.com/savya6/agentic_os",
                    "X-Title": "Agentic OS",
                })

            # Detect if we should use streaming to capture 'thinking' tokens (e.g. DeepSeek R1)
            use_stream = any(x in model.lower() for x in ["deepseek-r1", "reasoning", "thinking"])

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": use_stream
            }
            if stop:
                payload["stop"] = stop

            try:
                if use_stream:
                    # Capture thinking tokens via SSE stream
                    async with http_client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=httpx.Timeout(300.0, read=None)
                    ) as resp:
                        resp.raise_for_status()
                        full_content = []
                        full_thinking = []
                        
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                
                                # Standard content
                                content = delta.get("content", "")
                                if content:
                                    full_content.append(content)
                                
                                # Thinking/Reasoning content (supported by OpenRouter/DeepSeek)
                                reasoning = delta.get("reasoning_content", "")
                                if reasoning:
                                    full_thinking.append(reasoning)
                            except json.JSONDecodeError:
                                continue
                        
                        content = "".join(full_content)
                        thinking = "".join(full_thinking)
                        
                        if thinking.strip():
                            return f"<|thinking|>{thinking}<|/thinking|>\n{content}"
                        return content
                else:
                    # Standard unary call
                    resp = await http_client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=httpx.Timeout(120.0)
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
            except Exception as e:
                logger.error("[OpenAIBackend] Fetch error for model %s: %s", model, e)
                raise

        # Execute the batch concurrently
        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("[OpenAIBackend] Batch item failed: %s", r)
                processed.append(f"[Backend Error: {r}]")
            else:
                processed.append(str(r))
        return processed
