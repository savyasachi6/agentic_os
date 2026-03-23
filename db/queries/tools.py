"""
db/queries/tools.py
===================
Query layer for tool discovery and metadata management.
Replaces parts of agent_memory/vector_store.py.
"""
import logging
import json
from typing import List, Dict, Any, Optional
from db.connection import get_db_connection

logger = logging.getLogger("agentos.db.queries.tools")

def upsert_tool(name: str, description: str, risk_level: str, endpoint: str, docs: str, tags: List[str]) -> int:
    """Store or update a tool definition."""
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
                (name, description, risk_level, endpoint, docs, tags)
            )
            row = cur.fetchone()
            if not row:
                raise Exception("Tool upsert failed")
            conn.commit()
            return int(row[0])

def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a tool by its unique name."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, description, risk_level, endpoint FROM tools WHERE name = %s", (name,))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "name": row[1], "description": row[2], "risk_level": row[3], "endpoint": row[4]}
    return None
