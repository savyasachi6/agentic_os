"""
db/queries/thoughts.py
======================
Query layer for per-turn thoughts and session-level compacted summaries.
Replaces parts of agent_memory/vector_store.py.
"""
import logging
from typing import List, Dict, Any, Optional
from db.connection import get_db_connection

logger = logging.getLogger("agentos.db.queries.thoughts")

def log_thought(session_id: str, role: str, content: str, embedding: List[float]):
    """Store a thought or message with its embedding."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO thoughts (session_id, role, content, embedding) VALUES (%s, %s, %s, %s)",
                (session_id, role, content, embedding)
            )
        conn.commit()

def search_thoughts(query_vec: List[float], session_id: Optional[str] = None, limit: int = 5, strict_session: bool = False) -> List[Dict[str, Any]]:
    """Vector search over thoughts, optionally scoped to a session."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if session_id and strict_session:
                # Force hard filter for current session only (Phase 118 Hardening)
                cur.execute(
                    """
                    SELECT role, content, session_id, 1 - (embedding <=> %s::vector) AS score
                    FROM thoughts 
                    WHERE session_id = %s
                      AND 1 - (embedding <=> %s::vector) > 0.55
                    ORDER BY score DESC LIMIT %s
                    """,
                    (query_vec, session_id, query_vec, limit)
                )
            elif session_id:
                # Soft filter (prefer current session, but allows globality if needed - legacy logic)
                cur.execute(
                    """
                    SELECT role, content, session_id, 1 - (embedding <=> %s::vector) AS score
                    FROM thoughts 
                    WHERE (session_id = %s OR 1 - (embedding <=> %s::vector) > 0.70)
                      AND 1 - (embedding <=> %s::vector) > 0.55
                    ORDER BY score DESC LIMIT %s
                    """,
                    (query_vec, session_id, query_vec, query_vec, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT role, content, session_id, 1 - (embedding <=> %s::vector) AS score 
                    FROM thoughts 
                    WHERE 1 - (embedding <=> %s::vector) > 0.55
                    ORDER BY score DESC LIMIT %s
                    """,
                    (query_vec, query_vec, limit)
                )
            rows = cur.fetchall()
            return [{"role": r[0], "content": r[1], "session_id": r[2], "score": r[3]} for r in rows]

def store_session_summary(session_id: str, summary: str, embedding: List[float], turn_start: int, turn_end: int):
    """Store a compacted session summary."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO session_summaries (session_id, summary, embedding, turn_start, turn_end) VALUES (%s, %s, %s, %s, %s)",
                (session_id, summary, embedding, turn_start, turn_end)
            )
        conn.commit()

def retrieve_session_context(query_vec: List[float], session_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Fetch relevant session summaries for CoT continuity."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary, turn_start, turn_end, 1 - (embedding <=> %s::vector) AS score
                FROM session_summaries WHERE session_id = %s
                ORDER BY score DESC LIMIT %s
                """,
                (query_vec, session_id, limit)
            )
            rows = cur.fetchall()
            return [{"summary": r[0], "turn_start": r[1], "turn_end": r[2], "score": r[3]} for r in rows]
 
def get_all_sessions() -> List[Dict[str, Any]]:
    """Retrieve unique session IDs with a preview and creation timestamp."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Efficiently grab the earliest message for each session to provide a preview
            cur.execute("""
                SELECT DISTINCT ON (session_id) 
                    session_id, 
                    content as first_message, 
                    created_at
                FROM thoughts
                ORDER BY session_id, created_at ASC
            """)
            rows = cur.fetchall()
            return [
                {"session_id": r[0], "first_message": r[1], "created_at": r[2]} 
                for r in rows
            ]

def get_session_history(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve full history for a session, ordered by time."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, created_at FROM thoughts WHERE session_id = %s ORDER BY created_at ASC",
                (session_id,)
            )
            rows = cur.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2].isoformat()} for r in rows]

def get_last_compacted_turn(session_id: str) -> int:
    """Return the highest turn_end ever compacted for this session."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(turn_end), 0) FROM session_summaries WHERE session_id = %s",
                (session_id,)
            )
            return cur.fetchone()[0]

def delete_session(session_id: str):
    """Permanently delete all thoughts and summaries for a session."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM thoughts WHERE session_id = %s", (session_id,))
            cur.execute("DELETE FROM session_summaries WHERE session_id = %s", (session_id,))
        conn.commit()
