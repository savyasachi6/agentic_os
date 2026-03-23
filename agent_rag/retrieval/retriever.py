# agent_rag/retrieval/retriever.py
import time
from typing import List, Optional, Dict, Any

from agent_memory.rag_store import RagStore
from agent_memory.vector_store import VectorStore
from agent_memory.cache import SemanticCache

# New Enhancements
from .hyde import HyDERetriever
from ..rerankers.cross_encoder import CrossEncoderReranker


class RetrievedChunk:
    """Standardized DTO for items coming out of hybrid search."""
    def __init__(self, id: str, content: str, score: float, metadata: Dict[str, Any], relations: Optional[List[Dict]] = None):
        self.id = id
        self.content = content
        self.score = score
        self.metadata = metadata
        self.relations = relations or []


class HybridRetriever:
    """
    Abstracts dual semantic/lexical queries + relational graph traversal 
    away from the reasoning engine using raw Agent OS stores.
    """
    def __init__(self, top_k: int = 10):
        self._rag_store = RagStore()
        self._vector_store = VectorStore()
        self._semantic_cache = SemanticCache()
        self._top_k = top_k
        self._hyde = HyDERetriever()
        self._reranker = CrossEncoderReranker()


    def retrieve(self, query: str, session_id: str, top_k: Optional[int] = None, 
                 use_cache: bool = True, collapsed_tree_depth: int = 2,
                 use_hyde: bool = False, use_reranker: bool = False) -> List[RetrievedChunk]:
        start_time = time.time()
        k = top_k or self._top_k
        
        # 0. Latency Optimization: Semantic Caching
        if use_cache:
            cached = self._semantic_cache.get_cached_response(query)
            if cached:
                return self._parse_cached_chunks(cached["response"])

        # 1. HyDE (Speculative RAG) - Hypothetical Document Embedding
        is_hyde_fallback = False
        if use_hyde:
            # Note: HyDE normally needs async, but this is the sync retrieve()
            # We run it in a temp loop or executor if needed, but for sync we fallback
            # to plain embedding if we can't easily run async code here.
            # In practice, callers should use retrieve_async.
            query_vector, is_hyde_fallback = self._vector_store.generate_embedding(query)
        else:
            query_vector, _ = self._vector_store.generate_embedding(query)

        # 2. Execute hybrid search (Vector + Full-text) via RagStore
        # If reranking is enabled, we fetch more candidates (2*k) to ensure quality
        search_k = k * 2 if use_reranker else k
        results = self._rag_store.query_hybrid(query, query_vector, search_k)
        
        # Hydrate to DTOs
        final_chunks = [RetrievedChunk(
            id=r["id"],
            content=r["raw_text"],
            score=r["score"],
            metadata={
                "clean_text": r.get("clean_text"),
                "summary": r.get("llm_summary"),
                "source": r["source_uri"],
                "parent_chunk_id": r.get("parent_chunk_id")
            }
        ) for r in results]
        
        # 3. Cross-Encoder Re-Ranking
        if use_reranker and final_chunks:
            # Sync wrapper for reranking
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we are in an async loop, we cannot block and wait for a result 
                    # from the same loop. This is a design flaw in the sync retrieve().
                    # We log it and skip reranking to avoid deadlock.
                    print("[retriever] Warning: Skipping sync rerank from within an async loop to avoid deadlock. Use retrieve_async().")
                else:
                    final_chunks = asyncio.run(self._reranker.rerank(query, final_chunks, top_k=k))
            except Exception as e:
                print(f"[retriever] Sync Reranker failed: {e}")
                final_chunks = final_chunks[:k]
        
        # 4. Enrich structural relationships
        final_chunks = self._relational_search(final_chunks, depth=collapsed_tree_depth)
        
        # 5. Log the retrieval event
        latency_ms = int((time.time() - start_time) * 1000)
        strategy = "hybrid_merged"
        if use_hyde: strategy += "+hyde"
        if use_reranker: strategy += "+rerank"
        
        self._rag_store.log_retrieval_event(
            session_id=session_id,
            query=query,
            chunk_ids=[c.id for c in final_chunks],
            strategy=strategy,
            latency_ms=latency_ms
        )
        
        if use_cache:
            self._semantic_cache.set_cached_response(
                query=query, 
                response=[{"id": c.id, "content": c.content, "score": c.score, "metadata": c.metadata, "relations": c.relations} for c in final_chunks],
                strategy_used=strategy
            )
            
        return final_chunks

        
    async def retrieve_async(self, query: str, session_id: str, top_k: Optional[int] = None, 
                             use_cache: bool = True, collapsed_tree_depth: int = 2,
                             use_hyde: bool = False, use_reranker: bool = False) -> List[RetrievedChunk]:
        """Asynchronous version of retrieve to avoid blocking the event loop."""
        start_time = time.time()
        k = top_k or self._top_k
        
        if use_cache:
            cached = await self._semantic_cache.get_cached_response_async(query)
            if cached:
                return self._parse_cached_chunks(cached["response"])

        # 1. HyDE (Speculative RAG)
        if use_hyde:
            query_vector, _ = await self._hyde.generate_hyde_vector(query)
        else:
            query_vector, _ = await self._vector_store.generate_embedding_async(query)

        # 2. Hybrid Search
        search_k = k * 2 if use_reranker else k
        results = await self._rag_store.query_hybrid_async(query, query_vector, search_k)
        
        final_chunks = [RetrievedChunk(
            id=r["id"],
            content=r["raw_text"],
            score=r["score"],
            metadata={
                "clean_text": r.get("clean_text"),
                "summary": r.get("llm_summary"),
                "source": r["source_uri"],
                "parent_chunk_id": r.get("parent_chunk_id")
            }
        ) for r in results]
        
        # 3. Cross-Encoder Reranking
        if use_reranker and final_chunks:
            final_chunks = await self._reranker.rerank(query, final_chunks, top_k=k)
        
        # 4. Relational Search
        final_chunks = await self._relational_search_async(final_chunks, depth=collapsed_tree_depth)
        
        # 5. Logging & Cache
        latency_ms = int((time.time() - start_time) * 1000)
        strategy = "hybrid_merged_async"
        if use_hyde: strategy += "+hyde"
        if use_reranker: strategy += "+rerank"

        self._rag_store.log_retrieval_event(
            session_id=session_id,
            query=query,
            chunk_ids=[c.id for c in final_chunks],
            strategy=strategy,
            latency_ms=latency_ms
        )
        
        if use_cache:
            await self._semantic_cache.set_cached_response_async(
                query=query, 
                response=[{"id": c.id, "content": c.content, "score": c.score, "metadata": c.metadata, "relations": c.relations} for c in final_chunks],
                strategy_used=strategy
            )
            
        return final_chunks

        
    def _parse_cached_chunks(self, cached_payload: List[Dict]) -> List[RetrievedChunk]:
        """Hydrates JSON payloads from semantic cache back into domain objects."""
        if isinstance(cached_payload, str):
            import json
            cached_payload = json.loads(cached_payload)
            
        return [RetrievedChunk(
            id=r["id"],
            content=r["content"],
            score=r["score"],
            metadata=r.get("metadata", {}),
            relations=r.get("relations", [])
        ) for r in cached_payload]

    def _relational_search(self, chunks: List[RetrievedChunk], depth: int = 2) -> List[RetrievedChunk]:
        """Internal helper to hydrate graph relations for a set of chunks."""
        if not chunks:
            return chunks
        chunk_ids = [c.id for c in chunks]
        relations_map = self._rag_store.get_chunk_relations(chunk_ids)
        for chunk in chunks:
            chunk.relations = relations_map.get(chunk.id, [])
        return chunks

    async def _relational_search_async(self, chunks: List[RetrievedChunk], depth: int = 2) -> List[RetrievedChunk]:
        if not chunks:
            return chunks
        chunk_ids = [c.id for c in chunks]
        relations_map = await self._rag_store.get_chunk_relations_async(chunk_ids)
        for chunk in chunks:
            chunk.relations = relations_map.get(chunk.id, [])
        return chunks

    async def audit_results_async(self, event_id: str, auditor_role: str, score: float, chunk_id: Optional[str] = None, hallucination: bool = False, comments: str = ""):
        """Saves feedback from the validation agents (Auditor/Gatekeeper)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._rag_store.log_audit_feedback,
            event_id,
            chunk_id,
            auditor_role,
            score,
            hallucination,
            comments
        )

    async def speculative_retrieve(self, query: str, session_id: str,
                                    query_type: str = "analytical",
                                    shared_context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Async speculative retrieval using the Fractal RAG pipeline.
        Delegates to collapsed_tree_retrieve for the full draft-then-verify flow.
        """
        from agent_rag.retrieval.collapsed_tree import collapsed_tree_retrieve
        return await collapsed_tree_retrieve(
            query_type=query_type,
            query=query,
            session_id=session_id,
            shared_context=shared_context,
            top_k=self._top_k,
        )

