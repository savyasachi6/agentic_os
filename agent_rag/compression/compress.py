"""
Contextual Compression

After retrieval and re-ranking, each chunk may contain sentences irrelevant to the
current query.  This module distils each chunk down to only the facts that matter,
saving tokens and reducing noise before the context is sent to the drafter/verifier.

Usage
-----
    compressor = ContextualCompressor()
    compressed = await compressor.compress(query, chunks)
"""
import asyncio
import logging
from typing import List, Any

import ollama

from agent_config import model_settings

logger = logging.getLogger(__name__)

_COMPRESS_PROMPT = """\
You are a precise information extractor.  Your job is to rewrite the passage below \
keeping ONLY sentences that are directly relevant to the question.  Preserve all \
factual details, numbers, names, and dates.  Do NOT add any new information.  \
If nothing is relevant, respond with the single word: IRRELEVANT.

Question: {query}

Passage:
{passage}

Compressed passage:"""


class ContextualCompressor:
    """
    Compresses each retrieved chunk to query-relevant content only.

    Skips chunks whose compressed output would be empty or marked IRRELEVANT,
    making the final context window tighter and more focused.
    """

    def __init__(self, concurrency: int = 4, min_length: int = 10):
        self._model = model_settings.drafter_model
        self._sem = asyncio.Semaphore(concurrency)
        self._min_length = min_length

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compress(
        self,
        query: str,
        chunks: List[Any],      # List[RetrievedChunk]
    ) -> List[Any]:
        """
        Compress each chunk in *chunks* relative to *query*.

        Chunks with fully irrelevant content are dropped.
        Mutates `chunk.content` in-place and sets `chunk.metadata["compressed"] = True`.
        Returns the surviving (non-empty) chunks.
        """
        if not chunks:
            return chunks

        tasks = [self._compress_one(query, chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        surviving = []
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Compressor: failed to compress chunk %s, keeping original. Error: %s",
                    getattr(chunk, "id", "?"),
                    result,
                )
                surviving.append(chunk)
            elif result:
                surviving.append(chunk)
            # else: chunk was IRRELEVANT — drop it

        logger.debug(
            "Compressor: %d → %d chunks after compression for query: %s",
            len(chunks),
            len(surviving),
            query[:60],
        )
        return surviving

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _compress_one(self, query: str, chunk: Any) -> Any:
        """
        Compress a single chunk.  Returns the chunk (with mutated content) if
        something relevant remains, or None if the chunk should be dropped.
        """
        passage = (chunk.content or "")[:1200]  # generous but bounded
        if len(passage.strip()) < self._min_length:
            return None

        prompt = _COMPRESS_PROMPT.format(query=query, passage=passage)

        async with self._sem:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )

        compressed = response["message"]["content"].strip()

        if not compressed or compressed.upper() == "IRRELEVANT":
            return None

        # Store the original content in metadata for traceability
        chunk.metadata["original_content"] = chunk.content
        chunk.metadata["compressed"] = True
        chunk.content = compressed
        return chunk
