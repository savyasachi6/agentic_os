"""
Parent–Child Hierarchical Indexing

Splits a document into two granularity levels:
  • Parent chunks  (~1500 tokens / ~6000 chars) — rich context, NOT embedded.
  • Child  chunks  (~250  tokens / ~1000 chars) — search targets, embedded.

During retrieval, the system always searches child chunks (high precision).
When the Auditor signals low confidence, the Dynamic Zoomer fetches the parent
chunk (high context) to give the drafter more surrounding material.

Usage
-----
    builder = HierarchyBuilder(embed_fn=vector_store.generate_embedding_sync)
    parents, children = builder.build(document_id="doc-uuid", text=raw_text)

    # Index children via RagStore.upsert_chunks_with_embeddings()
    # Index parents as plain chunks with chunk_metadata["is_parent"] = True
"""
import hashlib
import logging
import re
import uuid
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (in characters, ~4 chars/token for English prose)
# ---------------------------------------------------------------------------
_DEFAULT_PARENT_SIZE = 6000    # ≈ 1500 tokens
_DEFAULT_CHILD_SIZE  = 1000    # ≈ 250  tokens
_DEFAULT_CHILD_OVERLAP = 100   # ≈ 25   tokens overlap between consecutive children


class HierarchyBuilder:
    """
    Builds a two-level (parent → children) chunk hierarchy for a document.

    Parameters
    ----------
    embed_fn:
        Sync callable that takes a text string and returns (embedding, is_fallback).
        Typically `VectorStore().generate_embedding_sync`.
    parent_size:
        Approximate character limit per parent chunk.
    child_size:
        Approximate character limit per child chunk.
    child_overlap:
        Character overlap between consecutive child chunks (sliding window).
    """

    def __init__(
        self,
        embed_fn: Callable[[str], Tuple[List[float], bool]],
        parent_size: int = _DEFAULT_PARENT_SIZE,
        child_size: int = _DEFAULT_CHILD_SIZE,
        child_overlap: int = _DEFAULT_CHILD_OVERLAP,
    ):
        self._embed_fn = embed_fn
        self._parent_size = parent_size
        self._child_size = child_size
        self._child_overlap = child_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self, document_id: str, text: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Split *text* into a parent/child hierarchy.

        Returns
        -------
        (parents, children)
            parents:  List of chunk dicts whose `chunk_metadata["is_parent"]` is True.
                      These should be indexed WITHOUT embeddings (or with a null
                      embedding) so they never appear in vector search results.
            children: List of chunk dicts with embeddings and `parent_chunk_id` set.
                      These are the actual search targets.
        """
        if not text or not text.strip():
            return [], []

        parent_texts = self._split_text(text, self._parent_size, overlap=0)
        parents: List[Dict] = []
        children: List[Dict] = []

        global_child_index = 0

        for p_idx, p_text in enumerate(parent_texts):
            parent_id = str(uuid.uuid4())
            parent_hash = _md5(p_text)

            parents.append({
                "id": parent_id,
                "document_id": document_id,
                "chunk_index": p_idx,
                "content_hash": parent_hash,
                "raw_text": p_text,
                "clean_text": _clean(p_text),
                "token_count": _approx_tokens(p_text),
                "section_path": f"parent/{p_idx}",
                "metadata": {"is_parent": True},
                "chunk_metadata": {"is_parent": True, "parent_index": p_idx},
                # Parents are NOT embedded — leave embedding absent
            })

            child_texts = self._split_text(
                p_text, self._child_size, overlap=self._child_overlap
            )
            for c_local_idx, c_text in enumerate(child_texts):
                embedding, is_fb = self._embed_fn(c_text)
                child_hash = _md5(c_text)

                children.append({
                    "id": str(uuid.uuid4()),
                    "document_id": document_id,
                    "chunk_index": global_child_index,
                    "content_hash": child_hash,
                    "raw_text": c_text,
                    "clean_text": _clean(c_text),
                    "token_count": _approx_tokens(c_text),
                    "section_path": f"parent/{p_idx}/child/{c_local_idx}",
                    "parent_chunk_id": parent_id,
                    "embedding": embedding,
                    "metadata": {
                        "is_parent": False,
                        "parent_chunk_id": parent_id,
                        "embedding_fallback": is_fb,
                    },
                    "chunk_metadata": {
                        "is_parent": False,
                        "parent_chunk_id": parent_id,
                        "parent_index": p_idx,
                        "child_local_index": c_local_idx,
                    },
                })
                global_child_index += 1

        logger.info(
            "HierarchyBuilder: document %s → %d parents, %d children",
            document_id,
            len(parents),
            len(children),
        )
        return parents, children

    # ------------------------------------------------------------------
    # Internal splitting
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text(text: str, max_chars: int, overlap: int = 0) -> List[str]:
        """
        Split *text* into chunks of at most *max_chars* characters.

        Attempts to split on paragraph boundaries first, then falls back to
        sentence boundaries, then hard-splits on the character limit.
        """
        if len(text) <= max_chars:
            return [text]

        chunks: List[str] = []
        start = 0

        while start < len(text):
            end = min(start + max_chars, len(text))
            segment = text[start:end]

            # Try to split on a paragraph boundary
            split_pos = _rfind_boundary(segment, ["\n\n", "\n", ". ", " "])
            if split_pos > max_chars // 2:
                segment = segment[:split_pos].rstrip()

            chunks.append(segment)
            # Advance with overlap
            start += len(segment) - overlap

        return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rfind_boundary(text: str, delimiters: List[str]) -> int:
    """Return the rightmost position of any delimiter in *text*, or 0."""
    best = 0
    for delim in delimiters:
        pos = text.rfind(delim)
        if pos > best:
            best = pos + len(delim)
    return best


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _clean(text: str) -> str:
    """Minimal cleanup: collapse whitespace, strip."""
    return re.sub(r"\s+", " ", text).strip()


def _approx_tokens(text: str) -> int:
    """Rough token count (words × 1.3)."""
    return int(len(text.split()) * 1.3)
