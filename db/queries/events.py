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
