from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator

class LLMBackend(ABC):
    @abstractmethod
    async def generate_batch(self, messages_batch: List[List[Dict[str, str]]], model: str, max_tokens: int, temperature: float, stop: Optional[List[str]] = None, tools: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """Generate responses for a batch of messages."""
        pass

    @abstractmethod
    async def generate_stream(self, messages: List[Dict[str, str]], model: str, max_tokens: int, temperature: float, stop: Optional[List[str]] = None, tools: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[Dict[str, str], None]:
        """Stream real-time tokens for a single request."""
        pass
