import asyncio
import logging
import json
import httpx
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import LLMBackend
from core.resilience import async_retry

logger = logging.getLogger("agentos.openai_backend")

_SHARED_CLIENT: httpx.AsyncClient | None = None

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
    Generic OpenAI-compatible backend (OpenRouter, Groq, local vLLM).
    Handles standard SSE (Server-Sent Events) for real-time streaming.
    """
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """
        Stream tokens for a single request using OpenAI SSE protocol.
        """
        http_client = _get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/savyasachi6/agentic_os",  # Required for OpenRouter
            "X-Title": "Agentic OS",                                 # Required for OpenRouter
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stop": stop,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with http_client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(300.0, read=None)
            ) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    logger.error(f"[OpenAIBackend] HTTP {resp.status_code}: {err_text.decode()}")
                    yield {"type": "error", "content": f"HTTP {resp.status_code}: {err_text.decode()}"}
                    return

                in_thinking_block = False
                token_buffer = ""

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data_str = line[len("data: "):].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data_str)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                        
                        # OpenRouter / Some providers use 'reasoning' or 'thought' fields
                        reasoning = delta.get("reasoning_content") or delta.get("thought")
                        content = delta.get("content", "")
                        tool_calls = delta.get("tool_calls")

                        if tool_calls:
                            yield {"type": "tool_call", "content": json.dumps(tool_calls)}
                            continue

                        if reasoning:
                            yield {"type": "thought", "content": reasoning}

                        if content:
                            token_buffer += content
                            # Standard thinking tag processing (same as Ollama)
                            while token_buffer:
                                starts = ["<|thinking|>", "<thinking>", "[thought]", "<|action|>", "<action>"]
                                ends = ["</|thinking|>", "</thinking>", "[/thought]", "</|action|>", "</action>"]
                                
                                if not in_thinking_block:
                                    best_start = -1
                                    best_tag = ""
                                    for start_tag in starts:
                                        idx = token_buffer.find(start_tag)
                                        if idx != -1 and (best_start == -1 or idx < best_start):
                                            best_start = idx
                                            best_tag = start_tag
                                    
                                    if best_start != -1:
                                        if best_start > 0:
                                            yield {"type": "token", "content": token_buffer[:best_start]}
                                        in_thinking_block = True
                                        token_buffer = token_buffer[best_start + len(best_tag):]
                                    else:
                                        # Yield tokens before potential partial tags
                                        safe_to_yield = -1
                                        for char in ['<', '[']:
                                            idx = token_buffer.find(char)
                                            if idx != -1 and (safe_to_yield == -1 or idx < safe_to_yield):
                                                safe_to_yield = idx
                                        
                                        if safe_to_yield != -1:
                                            if safe_to_yield > 0:
                                                yield {"type": "token", "content": token_buffer[:safe_to_yield]}
                                                token_buffer = token_buffer[safe_to_yield:]
                                            break # Wait for more data
                                        else:
                                            yield {"type": "token", "content": token_buffer}
                                            token_buffer = ""
                                else:
                                    best_end = -1
                                    best_tag = ""
                                    for end_tag in ends:
                                        idx = token_buffer.find(end_tag)
                                        if idx != -1 and (best_end == -1 or idx < best_end):
                                            best_end = idx
                                            best_tag = end_tag
                                            
                                    if best_end != -1:
                                        if best_end > 0:
                                            yield {"type": "thought", "content": token_buffer[:best_end]}
                                        in_thinking_block = False
                                        token_buffer = token_buffer[best_end + len(best_tag):]
                                    else:
                                        # Yield thoughts before potential partial tags
                                        safe_to_yield = -1
                                        for char in ['<', '[']:
                                            idx = token_buffer.find(char)
                                            if idx != -1 and (safe_to_yield == -1 or idx < safe_to_yield):
                                                safe_to_yield = idx
                                        
                                        if safe_to_yield != -1:
                                            if safe_to_yield > 0:
                                                yield {"type": "thought", "content": token_buffer[:safe_to_yield]}
                                                token_buffer = token_buffer[safe_to_yield:]
                                            break
                                        else:
                                            yield {"type": "thought", "content": token_buffer}
                                            token_buffer = ""

                    except json.JSONDecodeError:
                        continue
                
                # Final flush
                if token_buffer:
                    yield {"type": "thought" if in_thinking_block else "token", "content": token_buffer}

        except Exception as e:
            logger.error("[OpenAIBackend] Streaming error: %s", e)
            yield {"type": "error", "content": str(e)}

    async def generate_batch(
        self,
        messages_batch: List[List[Dict[str, str]]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None, # Added 'tools' argument
    ) -> List[str]:
        """
        Concurrency for batch processing using generate_stream.
        """
        async def fetch(messages: List[Dict[str, str]]) -> str:
            full_content = []
            full_thinking = []
            full_tool_calls = []
            
            async for chunk in self.generate_stream(messages, model, max_tokens, temperature, stop, tools):
                if chunk["type"] == "token":
                    full_content.append(chunk["content"])
                elif chunk["type"] == "thought":
                    full_thinking.append(chunk["content"])
                elif chunk["type"] == "tool_call":
                    full_tool_calls.append(chunk["content"])
                elif chunk["type"] == "error":
                    raise ValueError(chunk["content"])

            content = "".join(full_content)
            thinking = "".join(full_thinking)
            
            if full_tool_calls:
                return f"[TOOL_CALL_DETECTED] {full_tool_calls[-1]}"

            if thinking.strip():
                return f"<|thinking|>{thinking}<|/thinking|>\n{content}"
            return content

        tasks = [fetch(msgs) for msgs in messages_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("[OpenAIBackend] Batch item failed: %s", r)
                processed.append(f"[Error: {r}]")
            else:
                processed.append(str(r))
        return processed
