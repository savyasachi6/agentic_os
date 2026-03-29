"""
core/llm_client.py
==================
Consolidated LLM client for agentic_os.
Centralizes configuration, retry logic, and router interfacing.
"""
import logging
import asyncio
import json
from typing import List, Dict, Optional, Any, AsyncGenerator, Type
from pydantic import BaseModel

from core.settings import settings
from .router import LLMRouter
from .models import Priority

try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

logger = logging.getLogger("core.llm.client")

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
        # Use settings for defaults if not provided
        self.model_name = model_name
        if not self.model_name:
            if getattr(settings, "router_backend", "ollama") == "openai":
                self.model_name = settings.openai_model
            else:
                self.model_name = settings.ollama_model
        self.temperature = temperature if temperature is not None else 0.7
        self.max_tokens = max_tokens or 8192
        self.router = LLMRouter.get_instance()

    def _normalize_messages(self, messages: List[Any]) -> List[Dict[str, str]]:
        """
        Normalizes a list of messages into the standard List[Dict[str, str]] format.
        """
        normalized = []
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append(msg)
            elif HAS_LANGCHAIN and isinstance(msg, BaseMessage):
                role = "user"
                if isinstance(msg, HumanMessage): role = "user"
                elif isinstance(msg, AIMessage): role = "assistant"
                elif isinstance(msg, SystemMessage): role = "system"
                else:
                    role = getattr(msg, "type", "user")
                    if role == "ai": role = "assistant"
                
                normalized.append({"role": role, "content": str(msg.content or "")})
            elif isinstance(msg, str):
                normalized.append({"role": "user", "content": msg})
            else:
                # Handle dict or other objects
                role = "user"
                content = ""
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = str(msg.get("content") or "")
                else:
                    content = str(msg)
                
                normalized.append({"role": role, "content": content})
        return normalized

    async def generate_async(
        self,
        messages: List[Any],
        session_id: str = "default_session",
        priority: Priority = Priority.NORMAL,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Asynchronously generate a response via the router."""
        try:
            norm_messages = self._normalize_messages(messages)
            return await self.router.submit(
                messages=norm_messages,
                session_id=session_id,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                priority=priority,
                stop=stop,
                tools=tools
            )
        except Exception as e:
            logger.error("LLM Router error: %s", e)
            return f"[Agent error: {e}]"

    def generate(
        self,
        messages: List[Any],
        priority: Priority = Priority.NORMAL,
        stop: Optional[List[str]] = None
    ) -> str:
        """Synchronous wrapper."""
        try:
            loop = asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self.generate_async(messages, priority=priority, stop=stop))
        except RuntimeError:
            return asyncio.run(self.generate_async(messages, priority=priority, stop=stop))

    async def generate_streaming(
        self,
        messages: List[Any],
        session_id: str = "default_session",
        stop: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, str], None]:
        """
        Unified streaming generation via the LLMRouter.
        Yields chunks: {"type": "token"|"thought", "content": "..."}
        """
        norm_messages = self._normalize_messages(messages)
        try:
            async for chunk in self.router.stream(
                messages=norm_messages,
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stop=stop
            ):
                yield chunk
        except Exception as e:
            logger.error("LLM streaming error: %s", e)
            yield {"type": "error", "content": str(e)}

    def summarize(self, text: str) -> str:
        messages = [
            {"role": "system", "content": "Concise summary in 2-3 sentences."},
            {"role": "user", "content": text},
        ]
        return self.generate(messages, priority=Priority.SUMMARIZATION)

def get_llm() -> LLMClient:
    return LLMClient()
