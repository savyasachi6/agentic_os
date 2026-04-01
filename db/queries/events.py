"""
db/queries/events.py
====================
Query layer for system events and audit logs.
Replaces parts of agent_memory/vector_store.py.
"""
import logging
import json
from typing import Dict, Any
from db.connection import get_db_connection

logger = logging.getLogger("agentos.db.queries.events")

def log_event(session_id: str, source: str, event_type: str, data: Dict[str, Any]):
    """Store a system event."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (session_id, source, event_type, data) VALUES (%s, %s, %s, %s)",
                (session_id, source, event_type, json.dumps(data))
            )
        conn.commit()

def log_retrieval_event(
    session_id: str, 
    query_text: str, 
    strategy: str, 
    top_k: int, 
    chunk_ids: list[str], 
    latency_ms: int
):
    """Log a retrieval event for bandit feedback and performance auditing."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_events 
                (session_id, query_text, strategy_used, top_k, retrieved_chunk_ids, latency_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (session_id, query_text, strategy, top_k, chunk_ids, latency_ms)
            )
        conn.commit()
