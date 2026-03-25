"""
RagStore: Optimized Data Access Layer for Agent OS RAG.
Provides a clean interface for Document/Chunk storage, Skill Graph traversal, and Hybrid Retrieval.
"""
from typing import List, Dict, Any, Optional, Union
import json
import uuid
from uuid import UUID
from datetime import datetime

from db.connection import get_db_connection

class RagStore:
    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Document Management
    # ------------------------------------------------------------------
    def save_document(self, 
                        source_uri: str, 
                        source_type: str = "file",
                        title: Optional[str] = None,
                        author: Optional[str] = None,
                        language: str = "en",
                        metadata: Dict[str, Any] = {}) -> str:
        """Insert or update a document record. Returns document UUID string."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents (
                        source_type, source_uri, title, author, language, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_uri) DO UPDATE SET
                        source_type = EXCLUDED.source_type,
                        title = COALESCE(EXCLUDED.title, documents.title),
                        author = COALESCE(EXCLUDED.author, documents.author),
                        language = EXCLUDED.language,
                        metadata_json = documents.metadata_json || EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP,
                        deleted_at = NULL
                    RETURNING id;
                    """,
                    (source_type, source_uri, title, author, language, json.dumps(metadata)),
                )
                returned_id = str(cur.fetchone()[0])
            conn.commit()
            return returned_id

    # ------------------------------------------------------------------
    # Chunks and Embeddings
    # ------------------------------------------------------------------
    def upsert_chunks_with_embeddings(self, document_id: str, chunks: List[Dict[str, Any]], model_name: str):
        """
        Inserts a batch of chunks and their embedding vectors.
        Skips chunks that have an exact matching content_hash.
        `chunks` list items: {chunk_index, content_hash, raw_text, clean_text, token_count,
                              section_path, llm_summary, llm_tags, enrichment, metadata, embedding,
                              parent_chunk_id (optional — set by HierarchyBuilder for child chunks)}
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    content_hash = chunk.get("content_hash")
                    if content_hash:
                        cur.execute("SELECT id FROM chunks WHERE document_id = %s AND content_hash = %s LIMIT 1", (document_id, content_hash))
                        if cur.fetchone():
                            continue

                    chunk_id = chunk.get("id") or str(uuid.uuid4())
                    parent_chunk_id = chunk.get("parent_chunk_id")  # None for legacy / parent chunks

                    cur.execute(
                        """
                        INSERT INTO chunks (
                            id, document_id, chunk_index, content_hash, raw_text, clean_text,
                            token_count, section_path, llm_summary, llm_tags, enrichment_json,
                            chunk_metadata, parent_chunk_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                            content_hash = EXCLUDED.content_hash,
                            raw_text = EXCLUDED.raw_text,
                            clean_text = EXCLUDED.clean_text,
                            token_count = EXCLUDED.token_count,
                            section_path = EXCLUDED.section_path,
                            llm_summary = EXCLUDED.llm_summary,
                            llm_tags = EXCLUDED.llm_tags,
                            enrichment_json = EXCLUDED.enrichment_json,
                            chunk_metadata = EXCLUDED.chunk_metadata,
                            parent_chunk_id = EXCLUDED.parent_chunk_id,
                            updated_at = CURRENT_TIMESTAMP,
                            deleted_at = NULL
                        RETURNING id;
                        """,
                        (
                            chunk_id, document_id, chunk["chunk_index"], content_hash,
                            chunk["raw_text"], chunk.get("clean_text"),
                            chunk.get("token_count"), chunk.get("section_path"),
                            chunk.get("llm_summary"), chunk.get("llm_tags", []),
                            json.dumps(chunk.get("enrichment", {})),
                            json.dumps(chunk.get("metadata", {})),
                            parent_chunk_id,
                        )
                    )

                    persisted_chunk_id = cur.fetchone()[0]

                    if "embedding" in chunk:
                        cur.execute(
                            """
                            INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, is_current)
                            VALUES (%s, %s, %s, TRUE)
                            ON CONFLICT (chunk_id) DO UPDATE SET
                                embedding = EXCLUDED.embedding,
                                model_name = EXCLUDED.model_name,
                                is_current = EXCLUDED.is_current,
                                created_at = CURRENT_TIMESTAMP;
                            """,
                            (persisted_chunk_id, chunk["embedding"], model_name)
                        )
            conn.commit()

    # ------------------------------------------------------------------
    # Skill & Entity Management
    # ------------------------------------------------------------------
    def register_entity(self, name: str, entity_type: str, description: Optional[str] = None, metadata: Dict[str, Any] = {}) -> int:
        normalized_name = name.lower().replace(" ", "_").strip()
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entities (name, normalized_name, entity_type, description, metadata_json)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (normalized_name) DO UPDATE SET
                        name = EXCLUDED.name,
                        entity_type = EXCLUDED.entity_type,
                        description = COALESCE(EXCLUDED.description, entities.description),
                        metadata_json = entities.metadata_json || EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id;
                    """,
                    (name, normalized_name, entity_type, description, json.dumps(metadata))
                )
                entity_id = cur.fetchone()[0]
            conn.commit()
            return entity_id

    def link_entities(self, chunk_id: str, entity_id: int, confidence: float = 1.0, source: str = "llm_extraction"):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chunk_entities (chunk_id, entity_id, confidence, source)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chunk_id, entity_id) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        source = EXCLUDED.source,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (chunk_id, entity_id, confidence, source)
                )
            conn.commit()

    def insert_entity_relation(self, 
                                source_id: int, source_type: str, 
                                target_id: int, target_type: str, 
                                rel_type: str, weight: float = 1.0, 
                                metadata: Dict[str, Any] = {}):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entity_relations (
                        source_entity_id, source_entity_type, 
                        target_entity_id, target_entity_type, 
                        relation_type, weight, metadata_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_entity_id, target_entity_id, relation_type) DO UPDATE SET
                        weight = EXCLUDED.weight,
                        metadata_json = entity_relations.metadata_json || EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (source_id, source_type, target_id, target_type, rel_type, weight, json.dumps(metadata))
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def fetch_parent_chunk(self, parent_chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a parent chunk by its UUID for Dynamic Zooming.

        Returns a dict with 'id', 'raw_text', 'clean_text', 'chunk_metadata',
        or None if the chunk is not found.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, raw_text, clean_text, chunk_metadata
                    FROM chunks
                    WHERE id = %s AND deleted_at IS NULL
                    LIMIT 1;
                    """,
                    (parent_chunk_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": str(row[0]),
                    "raw_text": row[1],
                    "clean_text": row[2],
                    "chunk_metadata": row[3] or {},
                }

    async def fetch_parent_chunk_async(self, parent_chunk_id: str) -> Optional[Dict[str, Any]]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.fetch_parent_chunk, parent_chunk_id)

    def query_hybrid(self, query_text: str, query_vector: List[float], top_k: int = 10,
                     fulltext_weight: float = 0.5, vector_weight: float = 0.5) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval using RRF (Reciprocal Rank Fusion) on full-text and vector search.
        Returns a list of chunks with their scores and associated document info.
        Also returns parent_chunk_id when present (for Dynamic Zooming).
        """
        # Exclude parent-only chunks from search results (they have no embeddings and exist
        # only as context sources for zoom-out; we never want them as direct answers).
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH fulltext_search AS (
                        SELECT
                            c.id AS chunk_id,
                            c.document_id,
                            c.raw_text,
                            c.clean_text,
                            c.llm_summary,
                            c.parent_chunk_id,
                            d.source_uri,
                            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('english', c.clean_text), websearch_to_tsquery('english', %s)) DESC) AS rank
                        FROM chunks c
                        JOIN documents d ON c.document_id = d.id
                        WHERE to_tsvector('english', c.clean_text) @@ websearch_to_tsquery('english', %s)
                          AND (c.chunk_metadata->>'is_parent')::boolean IS NOT TRUE
                        ORDER BY rank
                        LIMIT %s
                    ),
                    vector_search AS (
                        SELECT
                            c.id AS chunk_id,
                            c.document_id,
                            c.raw_text,
                            c.clean_text,
                            c.llm_summary,
                            c.parent_chunk_id,
                            d.source_uri,
                            ROW_NUMBER() OVER (ORDER BY ce.embedding <=> %s::vector) AS rank
                        FROM chunks c
                        JOIN chunk_embeddings ce ON c.id = ce.chunk_id
                        JOIN documents d ON c.document_id = d.id
                        WHERE ce.is_current = TRUE
                          AND (c.chunk_metadata->>'is_parent')::boolean IS NOT TRUE
                        ORDER BY rank
                        LIMIT %s
                    ),
                    rrf_results AS (
                        SELECT
                            COALESCE(fs.chunk_id, vs.chunk_id) AS chunk_id,
                            (COALESCE(1.0 / (%s + fs.rank), 0.0) * %s +
                             COALESCE(1.0 / (%s + vs.rank), 0.0) * %s) AS score
                        FROM fulltext_search fs
                        FULL OUTER JOIN vector_search vs ON fs.chunk_id = vs.chunk_id
                    )
                    SELECT
                        COALESCE(fs.chunk_id, vs.chunk_id) AS id,
                        COALESCE(fs.document_id, vs.document_id) AS document_id,
                        COALESCE(fs.raw_text, vs.raw_text) AS raw_text,
                        COALESCE(fs.clean_text, vs.clean_text) AS clean_text,
                        COALESCE(fs.llm_summary, vs.llm_summary) AS llm_summary,
                        COALESCE(fs.source_uri, vs.source_uri) AS source_uri,
                        rr.score,
                        COALESCE(fs.parent_chunk_id, vs.parent_chunk_id) AS parent_chunk_id
                    FROM rrf_results rr
                    LEFT JOIN fulltext_search fs ON rr.chunk_id = fs.chunk_id
                    LEFT JOIN vector_search vs ON rr.chunk_id = vs.chunk_id
                    ORDER BY rr.score DESC
                    LIMIT %s;
                    """,
                    (query_text, query_text, top_k, query_vector, top_k,
                     60, fulltext_weight, 60, vector_weight, top_k)  # K=60 is a common RRF constant
                )
                rows = cur.fetchall()
                results = []
                for r in rows:
                    results.append({
                        "id": str(r[0]),
                        "document_id": str(r[1]),
                        "raw_text": r[2],
                        "clean_text": r[3],
                        "llm_summary": r[4],
                        "source_uri": r[5],
                        "score": float(r[6]),
                        "parent_chunk_id": str(r[7]) if r[7] else None,
                    })
                return results

    async def query_hybrid_async(self, query_text: str, query_vector: List[float], top_k: int = 10,
                                 fulltext_weight: float = 0.5, vector_weight: float = 0.5) -> List[Dict[str, Any]]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.query_hybrid, query_text, query_vector, top_k, fulltext_weight, vector_weight
        )

    def traverse_graph(self, entity_id: int, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Executes WITH RECURSIVE graph traversal to find related entities.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    WITH RECURSIVE graph_walk AS (
                        SELECT 
                            er.target_entity_id, 
                            er.relation_type, 
                            er.weight, 
                            1 AS depth,
                            ARRAY[er.source_entity_id, er.target_entity_id] AS path
                        FROM entity_relations er
                        WHERE er.source_entity_id = %s
                        
                        UNION ALL
                        
                        SELECT 
                            er.target_entity_id, 
                            er.relation_type, 
                            er.weight * gw.weight, 
                            gw.depth + 1,
                            gw.path || er.target_entity_id
                        FROM entity_relations er
                        INNER JOIN graph_walk gw ON er.source_entity_id = gw.target_entity_id
                        WHERE gw.depth < %s
                          AND er.target_entity_id <> ALL(gw.path) -- Avoid cycles
                    )
                    SELECT 
                        e.id, 
                        e.name, 
                        e.entity_type, 
                        gw.relation_type, 
                        gw.weight, 
                        gw.depth
                    FROM graph_walk gw
                    JOIN entities e ON gw.target_entity_id = e.id
                    ORDER BY gw.depth, gw.weight DESC;
                """
                cur.execute(query, (entity_id, max_depth))
                rows = cur.fetchall()
                return [{"id": r[0], "name": r[1], "type": r[2], "relation": r[3], "weight": float(r[4]), "depth": r[5]} for r in rows]

    def get_chunk_relations(self, chunk_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """ Retrieves entities associated with a batch of chunks. """
        if not chunk_ids: return {}
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ce.chunk_id, e.id, e.name, e.entity_type, ce.confidence
                    FROM chunk_entities ce
                    JOIN entities e ON ce.entity_id = e.id
                    WHERE ce.chunk_id = ANY(%s::uuid[])
                    """,
                    (chunk_ids,)
                )
                rows = cur.fetchall()
                res = {}
                for r in rows:
                    cid = str(r[0])
                    if cid not in res: res[cid] = []
                    res[cid].append({
                        "entity_id": r[1], "name": r[2], 
                        "type": r[3], "confidence": float(r[4])
                    })
                return res

    async def get_chunk_relations_async(self, chunk_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_chunk_relations, chunk_ids)

    # ------------------------------------------------------------------
    # Audit & Feedback
    # ------------------------------------------------------------------
    def log_retrieval_event(self, session_id: str, query: str, chunk_ids: List[str], strategy: str, latency_ms: int) -> str:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO retrieval_events (session_id, query_text, strategy_used, retrieved_chunk_ids, latency_ms)
                    VALUES (%s, %s, %s, %s::uuid[], %s)
                    RETURNING id;
                    """,
                    (session_id, query, strategy, chunk_ids, latency_ms)
                )
                event_id = str(cur.fetchone()[0])
            conn.commit()
            return event_id

    async def log_retrieval_event_async(self, session_id: str, query: str, chunk_ids: List[str], strategy: str, latency_ms: int) -> str:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.log_retrieval_event, session_id, query, chunk_ids, strategy, latency_ms
        )

    def log_audit_feedback(self, event_id: str, chunk_id: Optional[str], role: str, score: float, hallucination: bool = False, comments: str = ""):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if chunk_id:
                    cur.execute(
                        """
                        INSERT INTO event_chunks (event_id, chunk_id, auditor_relevance, hallucination_flag)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (event_id, chunk_id, score, hallucination)
                    )
                cur.execute(
                    """
                    INSERT INTO audit_feedback (retrieval_event_id, auditor_role, quality_score, hallucination_flag, comments)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (event_id, role, score, hallucination, comments)
                )
            conn.commit()

    async def log_audit_feedback_async(self, event_id: str, chunk_id: Optional[str], role: str, score: float, hallucination: bool = False, comments: str = ""):
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.log_audit_feedback, event_id, chunk_id, role, score, hallucination, comments
        )

    # ------------------------------------------------------------------
    # Speculative RAG: Draft Storage
    # ------------------------------------------------------------------
    def save_draft(self, draft_id: str, query_hash: str, draft_cluster: int,
                   draft_content: str, confidence: float, chunk_ids: List[str]) -> str:
        """Persist a speculative draft for traceability and caching."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rag_drafts (id, query_hash, draft_cluster, draft_content, confidence, chunk_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        draft_content = EXCLUDED.draft_content,
                        confidence = EXCLUDED.confidence
                    RETURNING id;
                    """,
                    (draft_id, query_hash, draft_cluster, draft_content, confidence, chunk_ids)
                )
                result = cur.fetchone()[0]
            conn.commit()
            return result

    async def save_draft_async(self, draft_id: str, query_hash: str, draft_cluster: int,
                               draft_content: str, confidence: float, chunk_ids: List[str]) -> str:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.save_draft, draft_id, query_hash, draft_cluster, draft_content, confidence, chunk_ids
        )

    def get_drafts_for_query(self, query_hash: str) -> List[Dict[str, Any]]:
        """Retrieve all stored drafts for a query, ordered by confidence DESC."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, query_hash, draft_cluster, draft_content, confidence, chunk_ids, created_at
                    FROM rag_drafts
                    WHERE query_hash = %s
                    ORDER BY confidence DESC;
                    """,
                    (query_hash,)
                )
                rows = cur.fetchall()
                return [{
                    "id": r[0], "query_hash": r[1], "draft_cluster": r[2],
                    "draft_content": r[3], "confidence": float(r[4]),
                    "chunk_ids": r[5] or [], "created_at": r[6]
                } for r in rows]

    # ------------------------------------------------------------------
    # Content Dependencies (Fractal Cache Staleness)
    # ------------------------------------------------------------------
    def upsert_content_dep(self, parent_hash: str, child_hash: str):
        """Register a parent→child content dependency for staleness tracking."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO content_deps (parent_hash, child_hash)
                    VALUES (%s, %s)
                    ON CONFLICT (parent_hash, child_hash) DO NOTHING;
                    """,
                    (parent_hash, child_hash)
                )
            conn.commit()

    def get_content_deps(self, parent_hash: str) -> List[str]:
        """Return all child content hashes that depend on a parent."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT child_hash FROM content_deps WHERE parent_hash = %s;",
                    (parent_hash,)
                )
                return [r[0] for r in cur.fetchall()]

