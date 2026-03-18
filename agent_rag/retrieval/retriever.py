# agent_rag/retrieval/retriever.py
import time
from typing import List, Optional, Dict, Any

from agent_memory.rag_store import RagStore
from agent_memory.vector_store import VectorStore
from agent_memory.cache import SemanticCache

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

    def retrieve(self, query: str, session_id: str, top_k: Optional[int] = None, 
                 use_cache: bool = True, collapsed_tree_depth: int = 2) -> List[RetrievedChunk]:
        start_time = time.time()
        k = top_k or self._top_k
        
        # 0. Latency Optimization: Semantic Caching
        if use_cache:
            cached = self._semantic_cache.get_cached_response(query)
            if cached:
                # Cache hit prevents full database scan
                return self._parse_cached_chunks(cached["response"])

        query_vector, _ = self._vector_store.generate_embedding(query)

        # 1. Execute hybrid search (Vector + Full-text) via RagStore
        results = self._rag_store.query_hybrid(query, query_vector, k)
        
        # Hydrate to DTOs
        final_chunks = [RetrievedChunk(
            id=r["id"],
            content=r["raw_text"],
            score=r["score"],
            metadata={
                "clean_text": r.get("clean_text"),
                "summary": r.get("llm_summary"),
                "source": r["source_uri"]
            }
        ) for r in results]
        
        # 2. Enrich the final set with structural relationships (Collapsed Tree)
        # Bypasses slow recursive layer-by-layer graph traversal by hitting the pre-computed edges up to N-depth
        final_chunks = self._relational_search(final_chunks, depth=collapsed_tree_depth)
        
        # 3. Log the retrieval event for audit/feedback loop
        latency_ms = int((time.time() - start_time) * 1000)
        chunk_ids = [c.id for c in final_chunks]
        self._rag_store.log_retrieval_event(
            session_id=session_id,
            query=query,
            chunk_ids=chunk_ids,
            strategy="hybrid_merged",
            latency_ms=latency_ms
        )
        
        # 4. Save to Semantic Cache for future identical/highly-similar queries
        if use_cache:
            self._semantic_cache.set_cached_response(
                query=query, 
                response=[{"id": c.id, "content": c.content, "score": c.score, "metadata": c.metadata, "relations": c.relations} for c in final_chunks],
                strategy_used="hybrid_merged"
            )
            
        return final_chunks
        
    async def retrieve_async(self, query: str, session_id: str, top_k: Optional[int] = None, 
                             use_cache: bool = True, collapsed_tree_depth: int = 2) -> List[RetrievedChunk]:
        """Asynchronous version of retrieve to avoid blocking the event loop."""
        start_time = time.time()
        k = top_k or self._top_k
        
        if use_cache:
            # Note: cache.get_cached_response is sync but fast (hash lookup)
            # However, vector search in cache is also sync. For robustness, we could make it async too.
            cached = self._semantic_cache.get_cached_response(query)
            if cached:
                return self._parse_cached_chunks(cached["response"])

        query_vector, _ = await self._vector_store.generate_embedding_async(query)

        # RagStore.query_hybrid is sync, we wrap it
        import asyncio
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, self._rag_store.query_hybrid, query, query_vector, k)
        
        final_chunks = [RetrievedChunk(
            id=r["id"],
            content=r["raw_text"],
            score=r["score"],
            metadata={
                "clean_text": r.get("clean_text"),
                "summary": r.get("llm_summary"),
                "source": r["source_uri"]
            }
        ) for r in results]
        
        final_chunks = await self._relational_search_async(final_chunks, depth=collapsed_tree_depth)
        
        latency_ms = int((time.time() - start_time) * 1000)
        self._rag_store.log_retrieval_event(
            session_id=session_id,
            query=query,
            chunk_ids=[c.id for c in final_chunks],
            strategy="hybrid_merged_async",
            latency_ms=latency_ms
        )
        
        if use_cache:
            await self._semantic_cache.set_cached_response_async(
                query=query, 
                response=[{"id": c.id, "content": c.content, "score": c.score, "metadata": c.metadata, "relations": c.relations} for c in final_chunks],
                strategy_used="hybrid_merged_async"
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
        import asyncio
        loop = asyncio.get_running_loop()
        chunk_ids = [c.id for c in chunks]
        relations_map = await loop.run_in_executor(None, self._rag_store.get_chunk_relations, chunk_ids)
        for chunk in chunks:
            chunk.relations = relations_map.get(chunk.id, [])
        return chunks

    def audit_results(self, event_id: str, auditor_role: str, score: float, chunk_id: Optional[str] = None, hallucination: bool = False, comments: str = ""):
        """Saves feedback from the validation agents (Auditor/Gatekeeper)."""
        self._rag_store.log_audit_feedback(
            event_id=event_id,
            chunk_id=chunk_id,
            role=auditor_role,
            score=score,
            hallucination=hallucination,
            comments=comments
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

