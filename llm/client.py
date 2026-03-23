"""
llm/client.py
=============
Unified LLM client for agentic_os.
Centralizes configuration, retry logic, and router interfacing.
Replaces the old agent_core/llm.py.
"""
import logging
import asyncio
import json
from typing import List, Dict, Optional, Any, AsyncGenerator, Type
from pydantic import BaseModel

from core.config import settings
from llm_router import LLMRouter # Temporarily until moved to llm/router.py
from llm_router.models import Priority

logger = logging.getLogger("agentos.llm.client")

class LLMClient:
    """
    Standard LLM client for all agentic_os components.
    Interfaces with the central LLMRouter for load balancing and priority.
    """
    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.model_name = model_name or settings.ollama_model
        self.temperature = temperature if temperature is not None else 0.7
        self.max_tokens = max_tokens or 2048
        self.router = LLMRouter.get_instance()

    async def generate_async(
        self,
        messages: List[Dict[str, str]],
        session_id: str = "default_session",
        priority: Priority = Priority.NORMAL,
        stop: Optional[List[str]] = None
    ) -> str:
        """Asynchronously generate a response via the router."""
        try:
            return await self.router.submit(
                messages=messages,
                session_id=session_id,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                priority=priority,
                stop=stop
            )
        except Exception as e:
            logger.error("LLM Router error: %s", e)
            return f"[Agent error: {e}]"

    def generate(
        self,
        messages: List[Dict[str, str]],
        priority: Priority = Priority.NORMAL,
        stop: Optional[List[str]] = None
    ) -> str:
        """
        Synchronous wrapper around generate_async.
        Uses nest_asyncio if called from an active loop.
        """
        try:
            loop = asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self.generate_async(messages, priority=priority, stop=stop))
        except RuntimeError:
            return asyncio.run(self.generate_async(messages, priority=priority, stop=stop))

    async def generate_streaming(
        self,
        messages: List[Dict[str, str]],
        stop: Optional[List[str]] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming generation bypassing the router for direct Ollama access."""
        from ollama import AsyncClient
        client = AsyncClient(host=settings.ollama_base_url)
        try:
            async for chunk in await client.chat(
                model=self.model_name,
                messages=messages,
                stream=True,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                    "stop": stop
                },
            ):
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
        except Exception as e:
            logger.error("LLM streaming error: %s", e)
            yield f"\n[LLM Stream Error] {e}"

    def summarize(self, text: str) -> str:
        """Produce a concise summary of the given text."""
        messages = [
            {"role": "system", "content": "Concise summary in 2-3 sentences."},
            {"role": "user", "content": text},
        ]
        return self.generate(messages, priority=Priority.SUMMARIZATION)

def get_llm() -> LLMClient:
    """Helper to return the default LLMClient."""
    return LLMClient()


async def generate_structured_output(
    prompt: str,
    response_model: Type[BaseModel],
    system_prompt: str = "You are a helpful assistant.",
    model_name: Optional[str] = None
) -> Any:
    """
    Helper to generate structured output (JSON) from an LLM and parse it into a Pydantic model.
    """
    client = LLMClient(model_name=model_name)
    
    # Simple JSON-enforcing prompt
    messages = [
        {"role": "system", "content": f"{system_prompt}\nReturn ONLY a valid JSON object matching this schema: {json.dumps(response_model.model_json_schema())}"},
        {"role": "user", "content": prompt}
    ]
    
    response = await client.generate_async(messages)
    
    # Attempt to parse JSON
    try:
        # Simple extraction if LLM wraps in backticks
        clean_response = response.strip()
        if "```json" in clean_response:
            clean_response = clean_response.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_response:
            clean_response = clean_response.split("```")[1].split("```")[0].strip()
            
        data = json.loads(clean_response)
        return response_model.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to parse structured output: {e}\nResponse: {response}")
        raise
