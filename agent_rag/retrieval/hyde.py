"""
HyDE — Hypothetical Document Embeddings

Instead of embedding the user's question directly, we first ask a fast LLM to
write a *hypothetical* answer, then embed that answer.  A hypothetical answer
looks much more like the documents that actually contain the answer, so the
cosine-similarity search finds better matches.

Usage
-----
    retriever = HyDERetriever()
    hyde_vec  = await retriever.generate_hyde_vector(query)
    # use hyde_vec instead of query_vector in rag_store.query_hybrid(...)
"""
import logging
from typing import List, Optional, Tuple

import ollama

from agent_config import model_settings
from agent_memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class HyDERetriever:
    """
    Generates a hypothetical document embedding for a query.

    The workflow is:
    1. Call the drafter LLM to speculatively answer the query in 2-3 sentences.
    2. Embed the speculative answer.
    3. Return the embedding vector.

    The caller can then use this vector instead of the raw query vector when
    calling `RagStore.query_hybrid()`.
    """

    def __init__(self):
        self._model = model_settings.drafter_model
        self._vector_store = VectorStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_hyde_vector(
        self, query: str
    ) -> Tuple[List[float], bool]:
        """
        Produce a HyDE embedding for *query*.

        Returns
        -------
        (embedding, is_fallback)
            is_fallback is True if we had to fall back to the plain query
            embedding (e.g. LLM was unavailable).
        """
        hypothetical = await self._generate_hypothetical_answer(query)
        if not hypothetical:
            logger.warning(
                "HyDE: hypothetical answer generation failed — "
                "falling back to plain query embedding"
            )
            return await self._vector_store.generate_embedding_async(query)

        embedding, is_fallback = await self._vector_store.generate_embedding_async(
            hypothetical
        )
        if is_fallback:
            logger.warning(
                "HyDE: embedding of hypothetical answer fell back to zero-vector"
            )

        logger.debug(
            "HyDE: generated hypothetical answer (%d chars) for query: %s",
            len(hypothetical),
            query[:80],
        )
        return embedding, is_fallback

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _generate_hypothetical_answer(self, query: str) -> Optional[str]:
        """
        Ask the fast drafter LLM to write a 2-3 sentence answer to *query*.
        We want fluent, document-like prose — not a chat response.
        """
        prompt = (
            "Write a concise, factual, 2-3 sentence passage that directly answers "
            "the following question. Write it as if you were writing a knowledge base "
            "article, not a chat reply. Do NOT say 'I' or 'The answer is'.\n\n"
            f"Question: {query}\n\n"
            "Passage:"
        )
        try:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response["message"]["content"].strip()
            return text if text else None
        except Exception as exc:
            logger.error("HyDE: LLM call failed: %s", exc)
            return None
