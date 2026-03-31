# db/queries.py
import asyncpg
import redis.asyncio as aioredis
import hashlib
import json
import numpy as np
import httpx
from core.settings import settings
from .connection import get_pool, get_redis

async def embed(text: str) -> list[float]:
    """Generate 1024-dim embedding via Ollama."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={"model": settings.ollama_model, "prompt": text}
        )
        return resp.json()["embedding"]

async def hybrid_search(
    query_text: str,
    query_embedding: list[float],
    match_limit: int = 5
) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM hybrid_search($1::vector, $2, $3)",
        query_embedding, query_text, match_limit
    )
    return [dict(r) for r in rows]

async def get_skill_inheritance_chain(normalized_name: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM get_skill_inheritance_chain($1)", normalized_name
    )
    return [dict(r) for r in rows]

async def check_redis_cache(query_hash: str) -> dict | None:
    r = await get_redis()
    val = await r.get(f"rag:{query_hash}")
    return json.loads(val) if val else None

async def check_semantic_cache(
    query_embedding: list[float],
    query_hash: str,
    threshold: float = 0.88
) -> dict | None:
    # L1: Redis exact hash
    r = await get_redis()
    val = await r.get(f"rag:{query_hash}")
    if val:
        return {"source": "redis", **json.loads(val)}

    # L2: pgvector similarity
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT response_payload, shared_context, strategy_used,
               1 - (query_vector <=> $1::vector) AS similarity
        FROM semantic_cache
        WHERE is_current = TRUE
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY query_vector <=> $1::vector
        LIMIT 1
    """, query_embedding)

    if row and row["similarity"] > threshold:
        return {"source": "pgvector", "similarity": row["similarity"],
                **json.loads(row["response_payload"])}
    return None

async def write_semantic_cache(
    query_hash: str,
    query_embedding: list[float],
    response_payload: dict,
    strategy: str,
    shared_context: dict = None
):
    pool = await get_pool()
    r = await get_redis()
    
    payload_json = json.dumps(response_payload)
    context_json = json.dumps(shared_context) if shared_context else None
    
    # Write to Postgres
    await pool.execute("""
        INSERT INTO semantic_cache 
            (query_hash, query_vector, response_payload, strategy_used, 
             shared_context, is_current, is_hot)
        VALUES ($1, $2::vector, $3, $4, $5, TRUE, FALSE)
        ON CONFLICT (query_hash) DO UPDATE SET
            response_payload = EXCLUDED.response_payload,
            is_current = TRUE,
            updated_at = NOW()
    """, query_hash, query_embedding, payload_json, strategy, context_json)
    
    # Write to Redis (L1)
    await r.setex(f"rag:{query_hash}", settings.cache_ttl_seconds, payload_json)
