import httpx
import asyncio
from typing import List, Dict
from llm_router.backends.base import LLMBackend

class OllamaBackend(LLMBackend):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def generate_batch(self, messages_batch: List[List[Dict[str, str]]], model: str, max_tokens: int, temperature: float) -> List[str]:
        """
        Ollama doesn't currently support a single batched API endpoint in the same way vLLM does.
        However, the Ollama server can handle concurrent requests natively. 
        We mimic batching here by firing concurrent async requests to Ollama.
        """
        async def fetch(client: httpx.AsyncClient, messages: List[Dict[str, str]]) -> str:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=httpx.Timeout(120.0)
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            except Exception as e:
                print(f"[OllamaBackend] Error generating response: {e}")
                return ""

        async with httpx.AsyncClient() as client:
            tasks = [fetch(client, msgs) for msgs in messages_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert exceptions to empty strings or error messages
            processed = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append(f"[Error: {r}]")
                else:
                    processed.append(str(r))
            return processed
