from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class LLMBackend(ABC):
    @abstractmethod
    async def generate_batch(self, messages_batch: List[List[Dict[str, str]]], model: str, max_tokens: int, temperature: float, stop: Optional[List[str]] = None) -> List[str]:
        """Generate responses for a batch of messages."""
        pass
