"""
Cross-Encoder Re-Ranking

After the initial bi-encoder vector search returns top-N candidates, this module
re-scores each (query, chunk) pair using the LLM as a cross-encoder.  The cross-
encoder sees both texts together, producing a much more accurate relevance score
than cosine distance alone.

We use the local Ollama drafter model (e.g. gemma3:1b) for scoring — no external
sentence-transformers dependency is needed.

Usage
-----
    reranker = CrossEncoderReranker()
    reranked  = await reranker.rerank(query, chunks, top_k=10)
"""
import asyncio
import logging
from typing import List, Any

import ollama

from agent_config import model_settings

logger = logging.getLogger(__name__)

_SCORE_PROMPT = """\
You are a relevance judge.  Given a query and a passage, rate how relevant the \
passage is to answering the query.

Query: {query}

Passage:
{passage}

Respond with a single float between 0.0 (irrelevant) and 1.0 (perfectly relevant). \
Output ONLY the number, nothing else."""


class CrossEncoderReranker:
    """
    LLM-based cross-encoder reranker.

    Rates each (query, chunk) pair and returns chunks sorted by that score,
    truncated to *top_k*.  Failures fall back to the original bi-encoder score
    so the pipeline never hard-fails.
    """

    def __init__(self, concurrency: int = 4):
        self._model = model_settings.drafter_model
        # Limit simultaneous LLM calls to avoid OOM on small machines
        self._sem = asyncio.Semaphore(concurrency)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rerank(
        self,
        query: str,
        chunks: List[Any],          # List[RetrievedChunk] (avoid circular import)
        top_k: int = 10,
    ) -> List[Any]:
        """
        Re-rank *chunks* against *query* and return the best *top_k*.

        Parameters
        ----------
        query:  The user query string.
        chunks: List of RetrievedChunk objects (must have .content and .score).
        top_k:  How many chunks to return after reranking.
        """
        if not chunks:
            return chunks

        tasks = [self._score_chunk(query, chunk) for chunk in chunks]
        scored = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for chunk, score in zip(chunks, scored):
            if isinstance(score, Exception):
                logger.warning(
                    "CrossEncoder: scoring failed for chunk %s, using bi-encoder score. Error: %s",
                    getattr(chunk, "id", "?"),
                    score,
                )
                # Keep the original bi-encoder score as a fallback
                results.append((chunk, chunk.score))
            else:
                results.append((chunk, score))

        results.sort(key=lambda x: x[1], reverse=True)
        reranked = [chunk for chunk, _ in results[:top_k]]

        # Update the .score attribute so downstream code stays consistent
        for chunk, new_score in results[:top_k]:
            chunk.score = new_score

        logger.debug(
            "CrossEncoder: reranked %d → %d chunks for query: %s",
            len(chunks),
            len(reranked),
            query[:60],
        )
        return reranked

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _score_chunk(self, query: str, chunk: Any) -> float:
        """Ask the LLM to score relevance of one (query, chunk) pair."""
        passage = (chunk.content or "")[:800]   # truncate to keep prompt small
        prompt = _SCORE_PROMPT.format(query=query, passage=passage)

        async with self._sem:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )

        raw = response["message"]["content"].strip()
        return _parse_float(raw, fallback=chunk.score)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_float(text: str, fallback: float = 0.5) -> float:
    """Extract the first float from *text*, return *fallback* on failure."""
    import re
    m = re.search(r"\d+\.\d+|\d+", text)
    if m:
        try:
            val = float(m.group())
            return min(max(val, 0.0), 1.0)
        except ValueError:
            pass
    return fallback
