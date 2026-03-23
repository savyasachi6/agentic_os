"""
db/queries/docs.py
==================
Query layer for appliance documentation and knowledge base chunks.
Replaces parts of agent_memory/vector_store.py.
"""
import logging
from typing import List, Dict, Any
from db.connection import get_db_connection

logger = logging.getLogger("agentos.db.queries.docs")

def search_docs(query_vec: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """Vector search over documentation chunks."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, d.title, d.source_uri, c.raw_text, d.source_type, 1 - (ce.embedding <=> %s::vector) AS score
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                JOIN chunk_embeddings ce ON c.id = ce.chunk_id
                ORDER BY score DESC LIMIT %s
                """,
                (query_vec, limit)
            )
            rows = cur.fetchall()
            return [
                {"id": str(r[0]), "title": r[1], "source_path": r[2], "content": r[3], "doc_type": r[4], "score": r[5]}
                for r in rows
            ]
