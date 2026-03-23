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
from .rl_client import RLRoutingClient
from agent_memory.cache import FractalCache

# New Enhancements
from .zoomer import DynamicZoomer
from ..compression.compress import ContextualCompressor


logger = logging.getLogger(__name__)

# Global default max recursion depth for fractal loops
MAX_FRACTAL_DEPTH = 3


async def collapsed_tree_retrieve(
    query_type: str,
    query: str,
    session_id: str,
    shared_context: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
    use_hyde: bool = True,
    use_reranker: bool = True,
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

    # Check cache first
    cached = await cache.get_cached_response_async(query)
    if cached:
        return {
            "answer": cached["response"],
            "strategy": cached["strategy"],
            "confidence": 1.0,
            "chunks": [],
            "from_cache": True,
        }

    # Dynamic Strategy Selection via RL Router
    rl_client = RLRoutingClient()
    depth, use_speculative, query_hash_rl, arm_index = await rl_client.route(query, session_id, query_type)

    if depth == 0:
        result = await _factual_direct_lookup(
            query, session_id, cache, top_k, use_reranker=use_reranker
        )
    else:
        result = await _speculative_pipeline(
            query, query_hash, session_id, cache,
            shared_context, top_k, max_depth=depth, use_speculative=use_speculative,
            use_hyde=use_hyde, use_reranker=use_reranker
        )

    
    # Enrich with routing metadata
    result["query_hash_rl"] = query_hash_rl
    result["arm_index"] = arm_index
    return result


async def _factual_direct_lookup(
    query: str, session_id: str, cache: FractalCache, top_k: int, use_reranker: bool = True
) -> Dict[str, Any]:

    """
    Flattened search bypassing layer-by-layer fractal traversal.
    Directly compares query embedding against all leaf and summary nodes.
    """
    retriever = HybridRetriever(top_k=top_k)
    chunks = await retriever.retrieve_async(
        query, session_id, use_cache=False, use_reranker=use_reranker
    )


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
    await cache.set_cached_response_async(query, answer, "factual_direct")
    return result


async def _speculative_pipeline(
    query: str,
    query_hash: str,
    session_id: str,
    cache: FractalCache,
    shared_context: Optional[Dict[str, Any]],
    top_k: int,
    max_depth: int = MAX_FRACTAL_DEPTH,
    use_speculative: bool = True,
    use_hyde: bool = True,      # Default ON for speculative
    use_reranker: bool = True,   # Default ON for speculative
) -> Dict[str, Any]:
    """
    Full speculative RAG pipeline:
    1. Retrieve chunks (with optional HyDE and Reranking)
    2. Audit (Quality Control)
    3. Zoom (Dynamic Resolution)
    4. Compress (Context Distillation)
    5. Draft & Verify
    6. Conditionally recurse
    """
    # 1. Retrieve
    retriever = HybridRetriever(top_k=top_k)
    chunks = await retriever.retrieve_async(
        query, session_id, use_cache=False, 
        use_hyde=use_hyde, use_reranker=use_reranker
    )

    if not chunks:
        return {"answer": "", "strategy": "speculative_empty", "confidence": 0.0, "chunks": []}

    # 2. Audit (Quality Control Gate)
    from agent_rag.validation.auditor import Auditor
    auditor = Auditor()
    approved_chunks, audit_reports = await auditor.audit_chunks(query, chunks)
    strategy_action = await auditor.evaluate_retrieval_strategy(query, audit_reports, chunks)


    # 3. Zoom (Dynamic Resolution)
    # If the auditor suggests zooming, we act on it before proceeding to drafting
    zoomer = DynamicZoomer()
    if strategy_action == "zoom_out":
        logger.info("Auditor suggested zoom_out. Attempting to fetch parent context.")
        zoomed_chunks = []
        for c in approved_chunks:
            parent_text = await zoomer.zoom_out(c)
            if parent_text:
                c.content = parent_text
                c.metadata["zoomed"] = "out"
            zoomed_chunks.append(c)
        approved_chunks = zoomed_chunks
    
    elif strategy_action == "zoom_in":
        logger.info("Auditor suggested zoom_in. Narrows focus to specific sentences.")
        zoomed_chunks = []
        for c in approved_chunks:
            sentences = zoomer.zoom_in(c)
            # For simplicity, we just pick the first sentence or keep the chunk
            # A more advanced version would re-rerank these sentences.
            if sentences:
                c.content = sentences[0] 
                c.metadata["zoomed"] = "in"
            zoomed_chunks.append(c)
        approved_chunks = zoomed_chunks

    if strategy_action == "pivot" and max_depth > 0:
        logger.info(f"Auditor suggested {strategy_action}, triggering resonance loop.")
        return await fractal_loop(
            query=query,
            spark=query,
            session_id=session_id,
            cache=cache,
            initial_answer="",
            initial_confidence=0.0,
            depth=1,
            max_depth=max_depth,
            use_speculative=use_speculative,
            feedback=strategy_action,
            use_hyde=use_hyde,
            use_reranker=use_reranker
        )

    if not approved_chunks:
        return {"answer": "I found some information, but it was rejected by the Auditor for quality issues.", 
                "strategy": "auditor_rejected", "confidence": 0.1, "chunks": chunks}

    # 4. Contextual Compression
    compressor = ContextualCompressor()
    compressed_chunks = await compressor.compress(query, approved_chunks)
    if compressed_chunks:
        approved_chunks = compressed_chunks

    # Convert chunks to drafter format
    chunk_dicts = [
        {"id": c.id, "content": c.content, "raw_text": c.content,
         "embedding": None, "score": c.score}
        for c in approved_chunks
    ]

    # 5. Draft & Verify
    if use_speculative:
        drafter = SpeculativeDrafter()
        drafts = await drafter.draft_parallel(query, chunk_dicts, shared_context)

        if not drafts:
            return {
                "answer": chunks[0].content if chunks else "",
                "strategy": "speculative_fallback",
                "confidence": 0.3,
                "chunks": chunks,
            }

        verifier = FractalVerifier()
        tree_context = _build_tree_context(chunks)
        verdict = await verifier.verify_fractal(query, drafts, tree_context)

        if verdict["confidence"] > 0.9:
            # Collapse tree — high confidence, return immediately
            await cache.set_cached_response_async(query, verdict["best_draft"], "speculative_collapsed")
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
                max_depth=max_depth,
                use_speculative=use_speculative,
            )
    else:
        # Depth > 0 but Speculative is OFF -> Direct recursive lookup (Multi-hop)
        # In this mode, we just use the first chunk as the "draft"
        return await fractal_loop(
            query=query,
            spark=query,
            session_id=session_id,
            cache=cache,
            initial_answer=chunks[0].content,
            initial_confidence=0.5,
            depth=1,
            max_depth=max_depth,
            use_speculative=use_speculative,
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
    use_speculative: bool = True,
    feedback: Optional[str] = None,
    use_hyde: bool = True,
    use_reranker: bool = True,
) -> Dict[str, Any]:

    """
    Recursive fractal branching: re-retrieves using the verifier's 'new_spark',
    generates new drafts, re-verifies, and either collapses or recurses again.
    
    Includes Auditor feedback-driven 'pivoting' or 'zooming'.
    """
    if depth > max_depth:
        logger.info(f"Fractal loop hit max depth ({max_depth}), returning best available answer")
        await cache.set_cached_response_async(query, initial_answer, "fractal_max_depth")
        return {
            "answer": initial_answer,
            "strategy": "fractal_max_depth",
            "confidence": initial_confidence,
            "chunks": [],
            "depth": depth,
        }

    logger.info(f"Fractal recursion depth={depth}, spark='{spark[:80]}...', feedback='{feedback}'")

    retriever = HybridRetriever()
    chunks = await retriever.retrieve_async(
        spark, session_id, use_cache=False,
        use_hyde=use_hyde, use_reranker=use_reranker
    )


    if not chunks:
        return {
            "answer": initial_answer,
            "strategy": "fractal_empty",
            "confidence": initial_confidence,
            "chunks": [],
            "depth": depth,
        }

    # Audit
    from agent_rag.validation.auditor import Auditor
    auditor = Auditor()
    approved_chunks, audit_reports = await auditor.audit_chunks(spark, chunks)
    strategy_action = await auditor.evaluate_retrieval_strategy(spark, audit_reports, chunks)


    if strategy_action in ["pivot", "zoom_in", "zoom_out"] and depth < max_depth:
        logger.info(f"Auditor suggested {strategy_action} at depth {depth}. Recursing with feedback.")
        return await fractal_loop(
            query=query,
            spark=spark, 
            session_id=session_id,
            cache=cache,
            initial_answer=initial_answer,
            initial_confidence=initial_confidence,
            depth=depth + 1,
            max_depth=max_depth,
            use_speculative=use_speculative,
            feedback=strategy_action,
            use_hyde=use_hyde,
            use_reranker=use_reranker
        )

    # 3. Zoom / Compress
    zoomer = DynamicZoomer()
    if strategy_action == "zoom_out":
        for c in approved_chunks:
            parent_text = await zoomer.zoom_out(c)
            if parent_text: c.content = parent_text
    elif strategy_action == "zoom_in":
        for c in approved_chunks:
            sentences = zoomer.zoom_in(c)
            if sentences: c.content = sentences[0]

    compressor = ContextualCompressor()
    approved_chunks = await compressor.compress(spark, approved_chunks)

    # 4. Draft & Verify

    if use_speculative:
        chunk_dicts = [
            {"id": c.id, "content": c.content, "raw_text": c.content, "embedding": None}
            for c in approved_chunks
        ]
        drafter = SpeculativeDrafter()
        drafts = await drafter.draft_parallel(spark, chunk_dicts)

        if not drafts:
            await cache.set_cached_response_async(query, initial_answer, "fractal_no_drafts")
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
            await cache.set_cached_response_async(query, final_answer, f"fractal_collapsed_d{depth}")
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
                use_speculative=use_speculative,
                feedback=None
            )
    else:
        # Non-speculative recursion (Multi-hop only)
        # We just use the top chunk from this layer as the answer and recurse if depth allows
        if depth >= max_depth:
             return {
                "answer": chunks[0].content if chunks else initial_answer,
                "strategy": f"fractal_non_spec_max_d{depth}",
                "confidence": 0.8,
                "chunks": chunks,
                "depth": depth,
            }
        
        return await fractal_loop(
            query=query,
            spark=chunks[0].content[:200] if chunks else spark,
            session_id=session_id,
            cache=cache,
            initial_answer=chunks[0].content if chunks else initial_answer,
            initial_confidence=0.5,
            depth=depth + 1,
            max_depth=max_depth,
            use_speculative=use_speculative,
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
