"""
db/queries/skills.py
====================
Query layer for skill discovery, indexing, and eval_lift tracking.
Replaces parts of agent_skills/indexer.py and agent_skills/retriever.py.
"""
import logging
from typing import List, Dict, Any, Optional
from db.connection import get_db_connection

logger = logging.getLogger("agentos.db.queries.skills")

def get_skill_metadata(normalized_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve skill metadata including checksum for incremental indexing."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, checksum FROM knowledge_skills WHERE normalized_name = %s", (normalized_name,))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "checksum": row[1]}
    return None

def update_skill_eval_lift(skill_id: int, new_lift: float):
    """Update the performance score of a skill based on feedback."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE knowledge_skills SET eval_lift = %s WHERE id = %s", (new_lift, skill_id))
        conn.commit()

def search_skills_raw(
    query_vec: List[float],
    limit: int = 10,
    skill_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Perform a pure vector search against skill_chunks with optional type filtering."""
    type_clause = "AND s.skill_type = %(skill_type)s" if skill_type else ""
    sql = f"""
        SELECT
            sc.skill_id, s.name, s.description, s.eval_lift,
            sc.heading, sc.content, sc.id AS chunk_id,
            1 - (sc.embedding <=> %(vec)s::vector) AS score
        FROM skill_chunks sc
        JOIN knowledge_skills s ON sc.skill_id = s.id
        WHERE 1=1 {type_clause}
        ORDER BY 
            (sc.embedding <=> %(vec)s::vector) 
            - (0.2 * COALESCE(s.eval_lift, 0.0)) ASC
        LIMIT %(limit)s;
    """
    params = {"vec": query_vec, "limit": limit}
    if skill_type:
        params["skill_type"] = skill_type

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                {
                    "skill_id": r[0], "skill_name": r[1], "skill_description": r[2],
                    "eval_lift": r[3], "heading": r[4], "content": r[5], 
                    "chunk_id": r[6], "score": r[7]
                } for r in rows
            ]
 
def upsert_skill(name: str, normalized_name: str, skill_type: str, description: str, aliases: List[str], path: str, checksum: str, eval_lift: float = 0.0) -> int:
    """Insert or update a skill record."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge_skills (name, normalized_name, skill_type, description, aliases, path, checksum, eval_lift)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (normalized_name) DO UPDATE SET
                    name = EXCLUDED.name,
                    skill_type = EXCLUDED.skill_type,
                    description = EXCLUDED.description,
                    aliases = EXCLUDED.aliases,
                    path = EXCLUDED.path,
                    checksum = EXCLUDED.checksum,
                    eval_lift = EXCLUDED.eval_lift,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
                """,
                (name, normalized_name, skill_type, description, aliases, path, checksum, eval_lift)
            )
            skill_id = cur.fetchone()[0]
        conn.commit()
    return skill_id

def delete_skill_chunks(skill_id: int):
    """Remove all chunks associated with a skill (usually before re-indexing)."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM skill_chunks WHERE skill_id = %s", (skill_id,))
        conn.commit()

def insert_skill_chunk(skill_id: int, chunk_type: str, heading: str, content: str, token_count: int, embedding: Optional[List[float]] = None):
    """Insert a single skill chunk. Note: embeddings should be handled by a separate process or updated later."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skill_chunks (skill_id, chunk_type, heading, content, token_count, embedding)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (skill_id, chunk_type, heading, content, token_count, embedding)
            )
        conn.commit()
