"""
rag/embedder.py
===============
Handles vector embedding generation via local Ollama or remote models.
Provides both sync and async interfaces.
Replaces the embedding logic in agent_memory/vector_store.py.
"""
import logging
import asyncio
from typing import List, Tuple, Optional
import ollama
from agent_core.config import settings

logger = logging.getLogger("agentos.rag.embedder")

class Embedder:
    """
    Standard embedder for agentic_os.
    Uses centralized configuration from core.config.
    """
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.ollama_model # Or a specific embedding model if separate
        self.dim = 1536 # Match schema.sql VECTOR(1536)

    def generate_embedding_sync(self, text: str) -> Tuple[List[float], bool]:
        """Generate a vector embedding. Returns (vector, is_fallback)."""
        if not text or not text.strip():
            return [0.0] * self.dim, True
            
        # Truncation to stay within model context limits
        safe_text = text[:4000]
        
        try:
            response = ollama.embeddings(model=self.model, prompt=safe_text)
            return response["embedding"], False
        except Exception as e:
            logger.warning("Embedding failed for text length %d: %s", len(text), e)
            return [0.0] * self.dim, True

    async def generate_embedding_async(self, text: str) -> Tuple[List[float], bool]:
        """Non-blocking embedding generation."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate_embedding_sync, text)
