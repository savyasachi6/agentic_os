import asyncio
import logging
import json
import httpx
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import LLMBackend
from core.resilience import async_retry, RETRYABLE_EXCEPTIONS

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
        Stream tokens for a single request using httpx.
        Yields chunks: {"type": "token"|"thought"|"tool_call", "content": "..."}
        """
        http_client = _get_client()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 16384,
                "stop": stop,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            async with http_client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=httpx.Timeout(300.0, read=None)
            ) as resp:
                resp.raise_for_status()
                
                in_thinking_block = False
                token_buffer = ""
                
                import time
                last_activity = time.time()
                
                async for line in resp.aiter_lines():
                    if not line:
                        # Check for inactivity timeout if we are expecting more but getting nothing
                        if time.time() - last_activity > 45.0:
                            raise TimeoutError("LLM streaming stalled for 45s")
                        continue
                    
                    last_activity = time.time()
                    chunk_data = json.loads(line)
                    msg = chunk_data.get("message", {})
                    
                    # Tool call logic for non-streaming response objects embedded in stream
                    if msg.get("tool_calls"):
                        yield {"type": "tool_call", "content": json.dumps(msg["tool_calls"])}
                        continue

                    content = msg.get("content", "")
                    thinking_field = msg.get("thinking", "")
                    
                    # 1. Handle explicit 'thinking' field (some models like DeepSeek-R1)
                    if thinking_field:
                        yield {"type": "thought", "content": thinking_field}
                    
                    # 2. Handle embedded tags in 'content'
                    if content:
                        token_buffer += content
                        
                        while token_buffer:
                            # 2.2 Define supported tags for reasoning/actions
                            # (Phase 45 Hardening: Support action tags and piped variants)
                            starts = ["<|thinking|>", "<thinking>", "[thought]", "<|action|>", "<action>"]
                            ends = ["</|thinking|>", "</thinking>", "[/thought]", "</|action|>", "</action>"]
                            
                            if not in_thinking_block:
                                # Look for ANY START of thinking block
                                best_start = -1
                                best_tag = ""
                                for start_tag in starts:
                                    idx = token_buffer.find(start_tag)
                                    if idx != -1 and (best_start == -1 or idx < best_start):
                                        best_start = idx
                                        best_tag = start_tag
                                
                                if best_start != -1:
                                    # Yield text before start tag as normal token
                                    if best_start > 0:
                                        yield {"type": "token", "content": token_buffer[:best_start]}
                                    
                                    in_thinking_block = True
                                    # Consume start tag
                                    token_buffer = token_buffer[best_start + len(best_tag):]
                                else:
                                    # NO tag found. Check for incomplete tag at end of buffer
                                    partial = False
                                    for start_tag in starts:
                                        # If the end of the buffer matches a prefix of any start tag
                                        for length in range(1, len(start_tag)):
                                            prefix = start_tag[:length]
                                            if token_buffer.endswith(prefix):
                                                partial = True
                                                break
                                        if partial: break
                                    
                                    if partial:
                                        # Entire buffer tail might be partial tag, wait for more data
                                        # Find the start of the first potential tag in the buffer
                                        # (Safe yield: everything before the first character that could start a tag)
                                        safe_to_yield = -1
                                        for char in ['<', '[']:
                                            idx = token_buffer.find(char)
                                            if idx != -1 and (safe_to_yield == -1 or idx < safe_to_yield):
                                                safe_to_yield = idx
                                        
                                        if safe_to_yield > 0:
                                            yield {"type": "token", "content": token_buffer[:safe_to_yield]}
                                            token_buffer = token_buffer[safe_to_yield:]
                                        break
                                    else:
                                        yield {"type": "token", "content": token_buffer}
                                        token_buffer = ""
                            else:
                                # Currently IN thinking block, look for ANY END
                                best_end = -1
                                best_tag = ""
                                for end_tag in ends:
                                    idx = token_buffer.find(end_tag)
                                    if idx != -1 and (best_end == -1 or idx < best_end):
                                        best_end = idx
                                        best_tag = end_tag
                                        
                                if best_end != -1:
                                    # Yield text before end tag as thought
                                    if best_end > 0:
                                        yield {"type": "thought", "content": token_buffer[:best_end]}
                                    
                                    in_thinking_block = False
                                    # Consume end tag
                                    token_buffer = token_buffer[best_end + len(best_tag):]
                                else:
                                    # NO end tag. Check for incomplete end tag
                                    partial = False
                                    for end_tag in ends:
                                        # If the end of the buffer matches a prefix of any end tag
                                        for length in range(1, len(end_tag)):
                                            prefix = end_tag[:length]
                                            if token_buffer.endswith(prefix):
                                                partial = True
                                                break
                                        if partial: break
                                            
                                    if partial:
                                        # Safe yield: everything before the first potential end tag start
                                        safe_to_yield = -1
                                        for char in ['<', '[']:
                                            idx = token_buffer.find(char)
                                            if idx != -1 and (safe_to_yield == -1 or idx < safe_to_yield):
                                                safe_to_yield = idx
                                        
                                        if safe_to_yield > 0:
                                            yield {"type": "thought", "content": token_buffer[:safe_to_yield]}
                                            token_buffer = token_buffer[safe_to_yield:]
                                        break
                                    else:
                                        yield {"type": "thought", "content": token_buffer}
                                        token_buffer = ""
                    if chunk_data.get("done"):
                        # Flush remaining buffer
                        if token_buffer:
                            yield {"type": "thought" if in_thinking_block else "token", "content": token_buffer}
                        break
        except Exception as e:
            logger.error("[OllamaBackend] Streaming error: %s", e)
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
        Fire concurrent async requests using the shared httpx pool directly.
        Consumes generate_stream for each item.
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
            
            if not content.strip() and not thinking.strip() and not full_tool_calls:
                raise ValueError("Ollama returned empty response.")
            
            # If there are tool calls, we return the JSON blob as the content for the router to pass back
            if full_tool_calls:
                # Return the last tool call blob if multiple, as typical for ReAct turn
                return f"[TOOL_CALL_DETECTED] {full_tool_calls[-1]}"

            if thinking.strip():
                return f"<|thinking|>{thinking}<|/thinking|>\n{content}"
            return content

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
