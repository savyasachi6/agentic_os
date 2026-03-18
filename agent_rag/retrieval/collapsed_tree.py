"""
Collapsed Tree Retrieval: Latency-optimized retrieval for the Fractal RAG pipeline.

- Factual queries → direct hybrid lookup (bypasses fractal traversal)
- Complex queries → SpeculativeDrafter → FractalVerifier → conditional fractal recursion
"""
import hashlib
import logging
from typing import Dict, Any, Optional, List

from .speculative_fractal_rag import SpeculativeDrafter, FractalVerifier
from .retriever import HybridRetriever, RetrievedChunk
from agent_memory.cache import FractalCache

logger = logging.getLogger(__name__)

# Global default max recursion depth for fractal loops
MAX_FRACTAL_DEPTH = 3


async def collapsed_tree_retrieve(
    query_type: str,
    query: str,
    session_id: str,
    shared_context: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Main entry point for latency-optimized retrieval.
    
    Args:
        query_type: 'factual' for direct lookup, 'analytical'/'multi-hop' for speculative pipeline
        query: The user query
        session_id: Current session ID
        shared_context: Optional pre-compiled context from SQL Architect
        top_k: Number of chunks to retrieve
        
    Returns:
        Dict with 'answer', 'strategy', 'confidence', 'chunks'
    """
    query_hash = hashlib.md5(query.strip().lower().encode('utf-8')).hexdigest()
    cache = FractalCache()

    # Check cache first (both factual and complex benefit)
    cached = cache.get_cached_response(query)
    if cached:
        return {
            "answer": cached["response"],
            "strategy": cached["strategy"],
            "confidence": 1.0,
            "chunks": [],
            "from_cache": True,
        }

    if query_type == "factual":
        return await _factual_direct_lookup(query, session_id, cache, top_k)
    else:
        return await _speculative_pipeline(query, query_hash, session_id, cache,
                                           shared_context, top_k)


async def _factual_direct_lookup(
    query: str, session_id: str, cache: FractalCache, top_k: int
) -> Dict[str, Any]:
    """
    Flattened search bypassing layer-by-layer fractal traversal.
    Directly compares query embedding against all leaf and summary nodes.
    """
    retriever = HybridRetriever(top_k=top_k)
    chunks = retriever.retrieve(query, session_id, use_cache=False)

    if not chunks:
        return {"answer": "", "strategy": "factual_empty", "confidence": 0.0, "chunks": []}

    # For factual queries, the top chunk is usually sufficient
    answer = chunks[0].content
    result = {
        "answer": answer,
        "strategy": "factual_direct",
        "confidence": chunks[0].score,
        "chunks": chunks,
    }

    # Cache the result
    cache.set_cached_response(query, answer, "factual_direct")
    return result


async def _speculative_pipeline(
    query: str,
    query_hash: str,
    session_id: str,
    cache: FractalCache,
    shared_context: Optional[Dict[str, Any]],
    top_k: int,
) -> Dict[str, Any]:
    """
    Full speculative RAG pipeline:
    1. Retrieve chunks
    2. Draft parallel answers
    3. Verify with fractal reflection
    4. Conditionally recurse
    """
    retriever = HybridRetriever(top_k=top_k)
    chunks = retriever.retrieve(query, session_id, use_cache=False)

    if not chunks:
        return {"answer": "", "strategy": "speculative_empty", "confidence": 0.0, "chunks": []}

    # Convert chunks to drafter format
    chunk_dicts = [
        {"id": c.id, "content": c.content, "raw_text": c.content,
         "embedding": None, "score": c.score}
        for c in chunks
    ]

    # Draft
    drafter = SpeculativeDrafter()
    drafts = await drafter.draft_parallel(query, chunk_dicts, shared_context)

    if not drafts:
        return {
            "answer": chunks[0].content if chunks else "",
            "strategy": "speculative_fallback",
            "confidence": 0.3,
            "chunks": chunks,
        }

    # Verify
    verifier = FractalVerifier()
    tree_context = _build_tree_context(chunks)
    verdict = await verifier.verify_fractal(query, drafts, tree_context)

    if verdict["confidence"] > 0.9:
        # Collapse tree — high confidence, return immediately
        cache.set_cached_response(query, verdict["best_draft"], "speculative_collapsed")
        return {
            "answer": verdict["best_draft"],
            "strategy": "speculative_collapsed",
            "confidence": verdict["confidence"],
            "chunks": chunks,
            "reasoning": verdict.get("reasoning", ""),
        }
    else:
        # Fractal recursion: follow the verifier's new_spark
        return await fractal_loop(
            query=query,
            spark=verdict.get("new_spark") or query,
            session_id=session_id,
            cache=cache,
            initial_answer=verdict["best_draft"],
            initial_confidence=verdict["confidence"],
            depth=1,
            max_depth=MAX_FRACTAL_DEPTH,
        )


async def fractal_loop(
    query: str,
    spark: str,
    session_id: str,
    cache: FractalCache,
    initial_answer: str = "",
    initial_confidence: float = 0.0,
    depth: int = 1,
    max_depth: int = MAX_FRACTAL_DEPTH,
) -> Dict[str, Any]:
    """
    Recursive fractal branching: re-retrieves using the verifier's 'new_spark',
    generates new drafts, re-verifies, and either collapses or recurses again.
    
    Terminates when:
    - confidence > 0.9
    - max_depth reached
    - verifier returns no new_spark
    """
    if depth > max_depth:
        logger.info(f"Fractal loop hit max depth ({max_depth}), returning best available answer")
        cache.set_cached_response(query, initial_answer, "fractal_max_depth")
        return {
            "answer": initial_answer,
            "strategy": "fractal_max_depth",
            "confidence": initial_confidence,
            "chunks": [],
            "depth": depth,
        }

    logger.info(f"Fractal recursion depth={depth}, spark='{spark[:80]}...'")

    retriever = HybridRetriever()
    chunks = retriever.retrieve(spark, session_id, use_cache=False)

    chunk_dicts = [
        {"id": c.id, "content": c.content, "raw_text": c.content, "embedding": None}
        for c in chunks
    ]

    drafter = SpeculativeDrafter()
    drafts = await drafter.draft_parallel(spark, chunk_dicts)

    if not drafts:
        cache.set_cached_response(query, initial_answer, "fractal_no_drafts")
        return {
            "answer": initial_answer,
            "strategy": "fractal_no_drafts",
            "confidence": initial_confidence,
            "chunks": chunks,
            "depth": depth,
        }

    verifier = FractalVerifier()
    tree_context = f"Previous best answer (depth {depth - 1}):\n{initial_answer[:500]}"
    verdict = await verifier.verify_fractal(spark, drafts, tree_context)

    if verdict["confidence"] > 0.9 or not verdict.get("new_spark"):
        # Collapse
        final_answer = verdict["best_draft"]
        cache.set_cached_response(query, final_answer, f"fractal_collapsed_d{depth}")
        return {
            "answer": final_answer,
            "strategy": f"fractal_collapsed_d{depth}",
            "confidence": verdict["confidence"],
            "chunks": chunks,
            "depth": depth,
        }
    else:
        # Recurse
        return await fractal_loop(
            query=query,
            spark=verdict["new_spark"],
            session_id=session_id,
            cache=cache,
            initial_answer=verdict["best_draft"],
            initial_confidence=verdict["confidence"],
            depth=depth + 1,
            max_depth=max_depth,
        )


def _build_tree_context(chunks: List[RetrievedChunk]) -> str:
    """Build a minimal tree context string from retrieved chunks."""
    if not chunks:
        return "(no context)"
    lines = []
    for i, c in enumerate(chunks[:5]):
        relations_str = ""
        if c.relations:
            rel_names = [r.get("name", r.get("target_name", "?")) for r in c.relations[:3]]
            relations_str = f" → [{', '.join(rel_names)}]"
        lines.append(f"  [{i}] score={c.score:.2f}{relations_str}: {c.content[:120]}...")
    return "\n".join(lines)
