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

def search_thoughts(query_vec: List[float], session_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Vector search over thoughts, optionally scoped to a session."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT role, content, 1 - (embedding <=> %s::vector) AS score
                    FROM thoughts WHERE session_id = %s
                    ORDER BY score DESC LIMIT %s
                    """,
                    (query_vec, session_id, limit)
                )
            else:
                cur.execute(
                    "SELECT role, content, 1 - (embedding <=> %s::vector) AS score FROM thoughts ORDER BY score DESC LIMIT %s",
                    (query_vec, limit)
                )
            rows = cur.fetchall()
            return [{"role": r[0], "content": r[1], "score": r[2]} for r in rows]

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
    """
    Retrieve unique session IDs with their topic and timestamp.
    Merges newer thoughts (first user message) with legacy session summaries.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Phase 3.5: Hybrid query to ensure data continuity
            cur.execute("""
                WITH latest_thoughts AS (
                    SELECT DISTINCT ON (session_id) 
                        session_id, 
                        content as topic, 
                        created_at 
                    FROM thoughts 
                    WHERE role = 'user'
                    ORDER BY session_id, created_at ASC
                ),
                latest_summaries AS (
                    SELECT DISTINCT ON (session_id)
                        session_id,
                        summary as topic,
                        created_at
                    FROM session_summaries
                    ORDER BY session_id, created_at DESC
                ),
                combined AS (
                    SELECT * FROM latest_thoughts
                    UNION
                    SELECT * FROM latest_summaries s 
                    WHERE NOT EXISTS (SELECT 1 FROM latest_thoughts t WHERE t.session_id = s.session_id)
                )
                SELECT session_id, topic, created_at FROM combined
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            return [
                {
                    "session_id": r[0],
                    "first_message": r[1],
                    "created_at": r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
                } for r in rows
            ]

def delete_session_data(session_id: str) -> None:
    """
    Hard-delete all data for a chat session.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Remove per-turn thoughts
            cur.execute("DELETE FROM thoughts WHERE session_id = %s", (session_id,))
            # Remove any compacted summaries
            cur.execute("DELETE FROM session_summaries WHERE session_id = %s", (session_id,))
        conn.commit()


def get_session_history(session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve full history for a session, ordered by time.
    Merges modern 'thoughts' with legacy 'session_summaries' for continuity.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Phase 4.0: Hybrid UNION query
            cur.execute(
                """
                WITH modern AS (
                    SELECT role, content, created_at FROM thoughts WHERE session_id = %s
                ),
                legacy AS (
                    SELECT 
                        'assistant' as role, 
                        '[Legacy Summary] ' || summary as content, 
                        created_at 
                    FROM session_summaries 
                    WHERE session_id = %s
                ),
                combined AS (
                    SELECT * FROM modern
                    UNION ALL
                    SELECT * FROM legacy
                )
                SELECT role, content, created_at FROM combined ORDER BY created_at ASC
                """,
                (session_id, session_id)
            )
            rows = cur.fetchall()
            return [
                {
                    "role": r[0], 
                    "content": r[1], 
                    "timestamp": r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
                } for r in rows
            ]
