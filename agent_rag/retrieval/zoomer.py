"""
Dynamic Zoomer

Provides "zoom in" and "zoom out" operations on retrieved chunks:

  zoom_out(chunk) → fetches the parent chunk from the DB.
    Use when the Auditor finds the chunk lacks sufficient context.

  zoom_in(chunk)  → splits the chunk into sentences.
    Use when the Auditor finds the chunk too broad ("noisy").

These are called from collapsed_tree.py in response to the Auditor's
strategy_action signal ("pivot" / "zoom_out" → zoom_out,  "zoom_in" → zoom_in).

Usage
-----
    zoomer = DynamicZoomer()
    parent_text = await zoomer.zoom_out(chunk)      # returns str or None
    sentences   = zoomer.zoom_in(chunk)             # returns List[str]
"""
import asyncio
import logging
import re
from typing import Any, List, Optional

from agent_memory.rag_store import RagStore

logger = logging.getLogger(__name__)


class DynamicZoomer:
    """
    Adaptive chunk granularity adjuster for the Fractal RAG pipeline.

    zoom_out — expands context by replacing a child chunk with its parent.
    zoom_in  — narrows focus by splitting a chunk into individual sentences.
    """

    def __init__(self):
        self._rag_store = RagStore()

    # ------------------------------------------------------------------
    # Zoom Out: fetch parent
    # ------------------------------------------------------------------

    async def zoom_out(self, chunk: Any) -> Optional[str]:
        """
        Retrieve the parent chunk text for *chunk*.

        Returns the parent's raw_text, or None if the chunk has no parent
        (i.e. it was indexed without hierarchy) or the parent is not found.
        """
        parent_id = (
            chunk.metadata.get("parent_chunk_id")
            if chunk.metadata
            else None
        )
        if not parent_id:
            logger.debug("DynamicZoomer.zoom_out: chunk %s has no parent_chunk_id", chunk.id)
            return None

        loop = asyncio.get_running_loop()
        parent = await loop.run_in_executor(
            None, self._rag_store.fetch_parent_chunk, parent_id
        )
        if not parent:
            logger.debug(
                "DynamicZoomer.zoom_out: parent %s not found in DB", parent_id
            )
            return None

        logger.debug(
            "DynamicZoomer.zoom_out: zoomed out chunk %s → parent %s (%d chars)",
            chunk.id,
            parent_id,
            len(parent.get("raw_text", "")),
        )
        return parent.get("raw_text") or parent.get("clean_text")

    # ------------------------------------------------------------------
    # Zoom In: sentence splitting
    # ------------------------------------------------------------------

    def zoom_in(self, chunk: Any) -> List[str]:
        """
        Split *chunk* content into individual sentences.

        Useful when the Auditor determines the chunk is too broad and a
        more focused sub-sentence is needed.  Returns a list of non-empty
        sentence strings.
        """
        text = chunk.content or ""
        sentences = _split_sentences(text)
        logger.debug(
            "DynamicZoomer.zoom_in: chunk %s → %d sentences",
            getattr(chunk, "id", "?"),
            len(sentences),
        )
        return sentences


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """
    Lightweight sentence splitter.
    Uses regex heuristics; does not need NLTK or spaCy.
    """
    # Split on sentence-ending punctuation followed by whitespace + capital letter
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text.strip())
    cleaned = [s.strip() for s in raw if s.strip()]
    return cleaned if cleaned else [text.strip()]
