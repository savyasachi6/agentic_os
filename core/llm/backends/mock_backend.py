import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator

from .base import LLMBackend

logger = logging.getLogger("agentos.mock_backend")

class MockBackend(LLMBackend):
    """
    Mock LLM provider for CI/CD and infrastructure debugging.
    Returns deterministic responses based on input patterns.
    """
    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Simple deterministic stream."""
        last_msg = messages[-1]["content"].lower()
        
        response = "I am the Agentic OS Mock Assistant. The real LLM backend is currently unreachable, but the orchestration infrastructure is operational."
        
        if "select" in last_msg or "schema" in last_msg:
            response = '{"thought": "I will scan the database schema.", "sql_query": "SELECT table_name FROM information_schema.tables WHERE table_schema = \'public\'"}'
        elif "hello" in last_msg or "hi" in last_msg:
            response = "Hello! I am the Agentic OS Coordinator (Mock Mode). How can I help you today?"
        
        # Simulate thinking
        yield {"type": "thought", "content": "Initializing mock response..."}
        await asyncio.sleep(0.1)
        
        # Stream tokens
        tokens = response.split(" ")
        for i, token in enumerate(tokens):
            yield {"type": "token", "content": token + (" " if i < len(tokens)-1 else "")}
            await asyncio.sleep(0.01)

    async def generate_batch(
        self,
        messages_batch: List[List[Dict[str, str]]],
        model: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]] = None,
    ) -> List[str]:
        results = []
        for msgs in messages_batch:
            full = ""
            async for chunk in self.generate_stream(msgs, model, max_tokens, temperature, stop):
                if chunk["type"] == "token":
                    full += chunk["content"]
            results.append(full)
        return results
