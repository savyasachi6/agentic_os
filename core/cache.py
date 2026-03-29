"""
FractalCache — Three-tier semantic cache.

  L0  Redis       — exact hash, sub-millisecond, in-memory, TTL-bounded
  L1  Postgres    — exact hash, persistent, survives restarts
  L2  pgvector    — semantic ANN similarity, catches paraphrase queries

Read path:  L0 hit → return immediately
            L0 miss → L1 hit → backfill L0 → return
            L1 miss → L2 hit → backfill L0+L1 → return
            full miss → return None (caller must compute + call set_*)

Write path: always writes L0, L1 (and embeds for L2) atomically.

Redis is optional: if the container is unreachable or REDIS_ENABLED=false,
the client degrades gracefully to Postgres-only (L1/L2) without any code
change at the call site.

Backward-compatible: `SemanticCache` alias is preserved.
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any

from db.connection import get_db_connection
from rag.vector_store import VectorStore
from .settings import settings
from urllib.parse import urlparse

logger = logging.getLogger("agentos.cache")


# ---------------------------------------------------------------------------
# Redis client — lazily initialised, silently disabled on error
# ---------------------------------------------------------------------------

def _make_redis_client():
    """Return a connected Redis client, or None if Redis is disabled/unreachable."""
    try:
        url = urlparse(settings.redis_url)
        import redis as redis_lib
        client = redis_lib.Redis(
            host=url.hostname or "127.0.0.1",
            port=url.port or 6379,
            password=url.password or None,
            db=int(url.path.lstrip('/') or 0),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        logger.info("[cache] Redis L0 connected at %s", settings.redis_url)
        return client
    except Exception as exc:
        logger.warning("[cache] Redis L0 unavailable (%s) — falling back to Postgres L1/L2", exc)
        return None


_redis_client = None
_redis_init_done = False


def _get_redis():
    """Lazy singleton. Returns None if Redis is down."""
    global _redis_client, _redis_init_done
    if not _redis_init_done:
        _redis_client = _make_redis_client()
        _redis_init_done = True
    return _redis_client


def _redis_key(query_hash: str, prefix: str = "cache") -> str:
    return f"agentos:{prefix}:{query_hash}"


# ---------------------------------------------------------------------------
# Main cache class
# ---------------------------------------------------------------------------

class FractalCache:
    """
    Advanced semantic cache implementing:
    - L0: Redis exact hash (sub-ms, in-process TTL)
    - L1: Postgres exact hash (O(1), persistent)
    - L2: pgvector semantic similarity (ANN via HNSW)
    - Shared Context: intermediate retrieval data for parallel agent queues
    - Staleness: content-dependency-aware invalidation via content_deps graph
    """

    def __init__(self, similarity_threshold: float = 0.95):
        self.vector_store = VectorStore()
        self.similarity_threshold = similarity_threshold

    # ------------------------------------------------------------------
    # L0  Redis helpers
    # ------------------------------------------------------------------

    def _l0_get(self, query_hash: str) -> Optional[Dict[str, Any]]:
        r = _get_redis()
        if r is None:
            return None
        try:
            raw = r.get(_redis_key(query_hash))
            if raw:
                logger.debug("[cache] L0 hit for %s", query_hash)
                return json.loads(raw)
        except Exception as exc:
            logger.warning("[cache] L0 read error: %s", exc)
        return None

    def _l0_set(self, query_hash: str, payload: Dict[str, Any]):
        r = _get_redis()
        if r is None:
            return
        try:
            ttl = getattr(settings, 'redis_ttl', 3600)
            serialised = json.dumps(payload)
            if ttl > 0:
                r.setex(_redis_key(query_hash), ttl, serialised)
            else:
                r.set(_redis_key(query_hash), serialised)
        except Exception as exc:
            logger.warning("[cache] L0 write error: %s", exc)

    def _l0_delete(self, query_hash: str):
        r = _get_redis()
        if r is None:
            return
        try:
            r.delete(_redis_key(query_hash))
        except Exception as exc:
            logger.warning("[cache] L0 delete error: %s", exc)

    # ------------------------------------------------------------------
    # L0 / L1 / L2 Cache Retrieval
    # ------------------------------------------------------------------

    async def get_cached_response_async(self, query: str) -> Optional[Dict[str, Any]]:
        """Non-blocking version of get_cached_response."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_cached_response, query)

    def get_cached_response(self, query: str) -> Optional[Dict[str, Any]]:
        """
        L0 Redis → L1 Postgres exact → L2 pgvector ANN.
        Returns None on miss, dict with 'response' + 'strategy' on hit.
        """
        query_hash = self._hash(query)

        # ── L0: Redis exact hash ──────────────────────────────────────
        l0_result = self._l0_get(query_hash)
        if l0_result is not None:
            return {**l0_result, "strategy": "l0_redis"}

        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # ── L1: Postgres exact hash ───────────────────────────
                cur.execute(
                    """
                    SELECT response_payload, staleness_version, is_current, content_hash
                    FROM semantic_cache
                    WHERE query_hash = %s
                    """,
                    (query_hash,),
                )
                row = cur.fetchone()
                if row and row[2]:  # is_current
                    self._touch_cache(cur, query_hash)
                    conn.commit()
                    result = {"response": row[0], "strategy": "l1_exact"}
                    self._l0_set(query_hash, result)   # backfill L0
                    return result

                # ── L2: pgvector semantic ANN ─────────────────────────
                query_vector, _ = self.vector_store.generate_embedding(query)
                cur.execute(
                    """
                    SELECT response_payload,
                           (1 - (query_vector <=> %s::vector)) AS similarity,
                           query_hash, content_hash
                    FROM semantic_cache
                    WHERE is_current = TRUE
                    ORDER BY query_vector <=> %s::vector
                    LIMIT 1
                    """,
                    (query_vector, query_vector),
                )
                row = cur.fetchone()
                if row and row[1] >= self.similarity_threshold:
                    content_hash = row[3]
                    if content_hash and not self.validate_staleness(content_hash):
                        return None

                    self._touch_cache(cur, row[2])
                    conn.commit()
                    result = {
                        "response": row[0],
                        "strategy": "l2_semantic",
                        "similarity": row[1],
                    }
                    # Backfill L0 under the *original* query hash so future
                    # identical queries skip even the vector search.
                    self._l0_set(query_hash, result)
                    return result

        return None

    def set_cached_response(
        self,
        query: str,
        response: Any,
        strategy_used: str,
        content_hash: Optional[str] = None,
    ):
        """Write a RAG response into all cache tiers (synchronous)."""
        query_hash = self._hash(query)
        query_vector, _ = self.vector_store.generate_embedding(query)
        payload = {"response": response, "strategy": strategy_used}

        # L1 + L2 (Postgres/pgvector)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO semantic_cache
                        (query_hash, query_vector, response_payload, strategy_used,
                         content_hash, is_current, hit_count)
                    VALUES (%s, %s, %s, %s, %s, TRUE, 0)
                    ON CONFLICT (query_hash) DO UPDATE SET
                        response_payload = EXCLUDED.response_payload,
                        strategy_used    = EXCLUDED.strategy_used,
                        content_hash     = EXCLUDED.content_hash,
                        is_current       = TRUE,
                        last_accessed_at = CURRENT_TIMESTAMP
                    """,
                    (query_hash, query_vector, json.dumps(response), strategy_used, content_hash),
                )
            conn.commit()

        # L0 (Redis) — only after Postgres write succeeds
        self._l0_set(query_hash, payload)

    async def set_cached_response_async(
        self,
        query: str,
        response: Any,
        strategy_used: str,
        content_hash: Optional[str] = None,
    ):
        """
        Non-blocking cache write — runs the sync embed + DB write in a thread
        executor so it never blocks the uvicorn/asyncio event loop.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self.set_cached_response(query, response, strategy_used, content_hash),
        )

    # ------------------------------------------------------------------
    # Shared Context (for parallel agent batches)
    # ------------------------------------------------------------------

    def get_shared_context(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve intermediate shared data compiled by SQL Architect for
        parallel Executor LLMs. Checks Redis first.
        """
        # L0 shared context uses a separate key prefix so it doesn't collide
        r = _get_redis()
        if r:
            try:
                raw = r.get(_redis_key(query_hash, prefix="ctx"))
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                logger.warning("[cache] L0 ctx read error: %s", exc)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT shared_context FROM semantic_cache
                    WHERE query_hash = %s AND is_current = TRUE
                    """,
                    (query_hash,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    self._touch_cache(cur, query_hash)
                    conn.commit()
                    data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    # Backfill L0
                    if r:
                        try:
                            ttl = getattr(settings, 'redis_ttl', 3600)
                            serialised = json.dumps(data)
                            if ttl > 0:
                                r.setex(_redis_key(query_hash, "ctx"), ttl, serialised)
                            else:
                                r.set(_redis_key(query_hash, "ctx"), serialised)
                        except Exception as exc:
                            logger.warning("[cache] L0 ctx backfill error: %s", exc)
                    return data
        return None

    def set_shared_context(self, query_hash: str, context_data: Dict[str, Any]):
        """Store intermediate retrieval results in the shared context tier."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO semantic_cache (query_hash, query_vector, response_payload,
                                                shared_context, is_current)
                    VALUES (%s, %s::vector, '{}'::jsonb, %s, TRUE)
                    ON CONFLICT (query_hash) DO UPDATE SET
                        shared_context   = EXCLUDED.shared_context,
                        is_current       = TRUE,
                        last_accessed_at = CURRENT_TIMESTAMP
                    """,
                    (query_hash, [0.0] * 1024, json.dumps(context_data)),
                )
            conn.commit()

        # Mirror to L0
        r = _get_redis()
        if r:
            try:
                ttl = getattr(settings, 'redis_ttl', 3600)
                serialised = json.dumps(context_data)
                if ttl > 0:
                    r.setex(_redis_key(query_hash, "ctx"), ttl, serialised)
                else:
                    r.set(_redis_key(query_hash, "ctx"), serialised)
            except Exception as exc:
                logger.warning("[cache] L0 ctx write error: %s", exc)

    # ------------------------------------------------------------------
    # Staleness Validation & Invalidation
    # ------------------------------------------------------------------

    def validate_staleness(self, content_hash: str) -> bool:
        """
        Fractal staleness check: verify that neither the entry itself
        nor its content dependencies have been invalidated.
        Returns True if content is still fresh.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT is_current FROM semantic_cache
                    WHERE content_hash = %s
                    AND NOT EXISTS (
                        SELECT 1 FROM content_deps cd
                        JOIN semantic_cache sc_dep ON sc_dep.content_hash = cd.child_hash
                        WHERE cd.parent_hash = %s AND sc_dep.is_current = FALSE
                    )
                    """,
                    (content_hash, content_hash),
                )
                row = cur.fetchone()
                return bool(row and row[0])

    def invalidate_dependencies(self, parent_hash: str):
        """
        Cascade invalidation: mark all cache entries whose content_hash
        appears as a child of parent_hash as stale, and evict from Redis L0.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Find affected hashes before marking stale so we can evict L0
                cur.execute(
                    """
                    SELECT query_hash FROM semantic_cache
                    WHERE content_hash IN (
                        SELECT child_hash FROM content_deps WHERE parent_hash = %s
                    )
                    """,
                    (parent_hash,),
                )
                affected = [r[0] for r in cur.fetchall()]

                cur.execute(
                    """
                    UPDATE semantic_cache SET is_current = FALSE
                    WHERE content_hash IN (
                        SELECT child_hash FROM content_deps WHERE parent_hash = %s
                    )
                    """,
                    (parent_hash,),
                )
                cur.execute(
                    "UPDATE semantic_cache SET is_current = FALSE WHERE content_hash = %s",
                    (parent_hash,),
                )
            conn.commit()

        # Evict stale entries from Redis L0
        for qh in affected:
            self._l0_delete(qh)

    def invalidate_stale_cache(self, staleness_version: int):
        """Legacy: invalidate entries older than staleness version."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM semantic_cache WHERE staleness_version < %s",
                    (staleness_version,),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _hash(self, query: str) -> str:
        return hashlib.md5(query.strip().lower().encode("utf-8")).hexdigest()

    def _touch_cache(self, cursor, query_hash: str):
        cursor.execute(
            "UPDATE semantic_cache SET last_accessed_at = CURRENT_TIMESTAMP, "
            "hit_count = hit_count + 1 WHERE query_hash = %s",
            (query_hash,),
        )


# Backward compatibility alias
SemanticCache = FractalCache
