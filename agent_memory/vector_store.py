"""
Vector store: embedding generation, skill CRUD, thought logging, and session memory.
All pgvector operations go through this module.
"""

import math
from typing import List, Dict, Any, Optional

import ollama
import os

from agent_config import model_settings
from .db import get_db_connection


class VectorStore:
    def __init__(self, embed_model: str = None):
        self.embed_model = embed_model or model_settings.embed_model

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    def generate_embedding_sync(self, text: str) -> tuple[List[float], bool]:
        """Generate a vector embedding via local Ollama. Returns (embedding, is_fallback)."""
        if not text or not text.strip():
            return [0.0] * model_settings.embed_dim, True

        # Conservative truncation for local embedding models (mxbai-embed-large / nomic)
        # 1000 chars is ~250-400 tokens, which is safe for almost all models.
        max_chars = 1000 
        safe_text = text[:max_chars]

        try:
            response = ollama.embeddings(model=self.embed_model, prompt=safe_text)
            return response["embedding"], False
        except Exception as e:
            # Fallback to zero-vector instead of crashing the transaction
            print(f"[vector_store] WARNING: Embedding failed for text of length {len(text)}. Falling back to zero-vector. Error: {e}")
            return [0.0] * model_settings.embed_dim, True

    async def generate_embedding_async(self, text: str) -> tuple[List[float], bool]:
        """Generate a vector embedding without blocking the asyncio loop."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate_embedding_sync, text)
        
    def generate_embedding(self, text: str) -> tuple[List[float], bool]:
        """
        Backward-compatible sync entry point. 
        WARNING: If called from within an async loop, this will block the loop.
        Callers in async contexts should use await generate_embedding_async().
        """
        return self.generate_embedding_sync(text)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------
    def upsert_skill(
        self, name: str, description: str, tags: List[str], path: str, checksum: str = None, eval_lift: float = 0.0
    ) -> int:
        """
        Insert or update a skill by name (ON CONFLICT).
        
        Args:
            name: Human-readable name of the skill.
            description: Brief description of the skill's purpose.
            tags: List of associated tags.
            path: Hierarchical path (e.g., 'category/subcategory').
            checksum: Optional content hash for staleness detection.
            eval_lift: Metric for skill effectiveness.
            
        Returns:
            The database ID of the skill.
        """
        # Use path-based normalization if available
        normalized_name = path.lower().replace(" ", "_").replace("/", "_").replace("\\", "_") if path else name.lower().replace(" ", "_")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_skills (name, normalized_name, skill_type, description, metadata_json, path, checksum, eval_lift)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (normalized_name) DO UPDATE SET
                        name = EXCLUDED.name,
                        skill_type = EXCLUDED.skill_type,
                        description = EXCLUDED.description,
                        metadata_json = EXCLUDED.metadata_json,
                        path        = EXCLUDED.path,
                        checksum    = EXCLUDED.checksum,
                        eval_lift   = EXCLUDED.eval_lift
                    RETURNING id;
                    """,
                    (name, normalized_name, "concept", description, "{}", path, checksum, eval_lift),
                )
                skill_id = cur.fetchone()[0]
            conn.commit()
            return skill_id

    def delete_skill_chunks(self, skill_id: int):
        """Remove all chunks for a skill (used before re-indexing)."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM skill_chunks WHERE skill_id = %s;", (skill_id,))
            conn.commit()

    def insert_skill_chunk(
        self,
        skill_id: int,
        chunk_type: str,
        heading: str,
        content: str,
        token_count: int,
    ):
        """
        Embeds and stores a single skill chunk in the database.
        
        Args:
            skill_id: ID of the parent skill.
            chunk_type: Category of chunk (e.g., 'instruction', 'example').
            heading: Section heading for context.
            content: Raw text content of the chunk.
            token_count: Estimated token count for the content.
        """
        embedding, _ = self.generate_embedding(content)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skill_chunks (skill_id, chunk_type, heading, content, embedding, token_count)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (skill_id, chunk_type, heading, content, embedding, token_count),
                )
            conn.commit()

    def search_skills(self, query: str, limit: int = 8) -> tuple[List[Dict[str, Any]], bool]:
        """Performs search. Returns (results, is_degraded)."""
        query_vec, is_degraded = self.generate_embedding(query)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        s.id, s.name, s.description, s.eval_lift,
                        c.chunk_type, c.heading, c.content,
                        1 - (c.embedding <=> %s::vector) AS score
                    FROM skill_chunks c
                    JOIN knowledge_skills s ON c.skill_id = s.id
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vec, query_vec, limit),
                )
                columns = [
                    "skill_id", "skill_name", "skill_description", "eval_lift",
                    "chunk_type", "heading", "content", "score",
                ]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return results, is_degraded

    # ------------------------------------------------------------------
    # Thoughts (per-turn reasoning log)
    # ------------------------------------------------------------------
    def log_thought(self, session_id: str, role: str, content: str):
        """Store a thought / message with its embedding."""
        try:
            if not content or not content.strip():
                embedding = [0.0] * model_settings.embed_dim
            else:
                embedding, _ = self.generate_embedding(content)
                
            if not embedding or len(embedding) == 0:
                embedding = [0.0] * model_settings.embed_dim
                
        except Exception as e:
            print(f"[vector_store] Error embedding thought, falling back to 0-vector: {e}")
            embedding = [0.0] * model_settings.embed_dim

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO thoughts (session_id, role, content, embedding)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (session_id, role, content, embedding),
                )
            conn.commit()

    def search_thoughts(
        self, query: str, session_id: Optional[str] = None, limit: int = 5
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Vector search over thoughts. Returns (results, is_degraded)."""
        query_vec, is_degraded = self.generate_embedding(query)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if session_id:
                    cur.execute(
                        """
                        SELECT session_id, role, content,
                               1 - (embedding <=> %s::vector) AS score
                        FROM thoughts
                        WHERE session_id = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s;
                        """,
                        (query_vec, session_id, query_vec, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT session_id, role, content,
                               1 - (embedding <=> %s::vector) AS score
                        FROM thoughts
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s;
                        """,
                        (query_vec, query_vec, limit),
                    )
                columns = ["session_id", "role", "content", "score"]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return results, is_degraded

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve chronological history of thoughts/messages for a session to hydrate a UI."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content, created_at
                    FROM thoughts
                    WHERE session_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (session_id,)
                )
                columns = ["role", "content", "created_at"]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Session summaries (compacted CoT memory)
    # ------------------------------------------------------------------
    def store_session_summary(
        self, session_id: str, summary: str, turn_start: int, turn_end: int
    ):
        """Store a compacted session summary with embedding."""
        embedding, _ = self.generate_embedding(summary)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_summaries (session_id, summary, embedding, turn_start, turn_end)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (session_id, summary, embedding, turn_start, turn_end),
                )
            conn.commit()

    def retrieve_session_context(
        self, query: str, session_id: str, limit: int = 3
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Fetch relevant session summaries. Returns (results, is_degraded)."""
        query_vec, is_degraded = self.generate_embedding(query)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT summary, turn_start, turn_end,
                           1 - (embedding <=> %s::vector) AS score
                    FROM session_summaries
                    WHERE session_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vec, session_id, query_vec, limit),
                )
                columns = ["summary", "turn_start", "turn_end", "score"]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return results, is_degraded

    # ------------------------------------------------------------------
    # System & Tools Data
    # ------------------------------------------------------------------
    def log_event(self, session_id: str, source: str, event_type: str, data: Dict[str, Any]):
        import json
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events (session_id, source, event_type, data)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (session_id, source, event_type, json.dumps(data)),
                )
            conn.commit()
            
    def upsert_tool(
        self, name: str, description: str, risk_level: str, endpoint: str, docs: str, tags: List[str]
    ) -> int:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tools (name, description, risk_level, endpoint, docs, tags)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        description = EXCLUDED.description,
                        risk_level  = EXCLUDED.risk_level,
                        endpoint    = EXCLUDED.endpoint,
                        docs        = EXCLUDED.docs,
                        tags        = EXCLUDED.tags
                    RETURNING id;
                    """,
                    (name, description, risk_level, endpoint, docs, tags),
                )
                tool_id = cur.fetchone()[0]
            conn.commit()
            return tool_id
            
    # ------------------------------------------------------------------
    # Appliance RAG (Docs)
    # ------------------------------------------------------------------
    def insert_doc_chunk(self, title: str, source_path: str, content: str, doc_type: str, tags: List[str]):
        embedding, _ = self.generate_embedding(content)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO docs (title, source_path, content, embedding, doc_type, tags)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (title, source_path, content, embedding, doc_type, tags),
                )
            conn.commit()
            
    def search_docs(self, query: str, limit: int = 5) -> tuple[List[Dict[str, Any]], bool]:
        """Search docs. Returns (results, is_degraded)."""
        query_vec, is_degraded = self.generate_embedding(query)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, source_path, content, doc_type,
                           1 - (embedding <=> %s::vector) AS score
                    FROM docs
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vec, query_vec, limit),
                )
                columns = ["id", "title", "source_path", "content", "doc_type", "score"]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return results, is_degraded
