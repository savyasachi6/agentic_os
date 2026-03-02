import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from agent_memory.db import get_db_connection
from agent_rag.validation.agents import AuditorAgent
from agent_rag.retrieval.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

class QueueManager:
    """
    Manages Dynamic Priority Queues (DAGs) for Agent OS executions.
    Supports topological dispatch and Auditor-driven re-prioritization.
    """
    def __init__(self, session_id: str, lane_id: str):
        self.session_id = session_id
        self.lane_id = lane_id

    def enqueue_command(self, cmd_type: str, payload: Dict[str, Any], depends_on: List[str] = None, priority: int = 5) -> str:
        """Enqueues a new command into the DAG with explicit dependencies."""
        cmd_id = payload.get("id") or f"cmd_{int(datetime.now().timestamp() * 1000)}"
        deps = depends_on or []
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get max sequence essentially as a fallback order
                cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM commands WHERE lane_id = %s", (self.lane_id,))
                seq = cur.fetchone()[0]
                
                cur.execute(
                    """
                    INSERT INTO commands (
                        id, lane_id, seq, cmd_type, payload, priority, depends_on, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                    RETURNING id;
                    """,
                    (cmd_id, self.lane_id, seq, cmd_type, json.dumps(payload), priority, deps)
                )
            conn.commit()
            return cmd_id

    def get_next_runnable(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the highest priority command whose dependencies are all 'done'.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH resolved_deps AS (
                        SELECT c.id
                        FROM commands c
                        WHERE c.lane_id = %s AND c.status = 'pending'
                        AND NOT EXISTS (
                            SELECT 1
                            FROM unnest(c.depends_on) AS dep_id
                            JOIN commands dep_c ON dep_c.id = dep_id
                            WHERE dep_c.status != 'done'
                        )
                    )
                    SELECT id, cmd_type, payload, priority, depends_on
                    FROM commands
                    WHERE id IN (SELECT id FROM resolved_deps)
                    ORDER BY priority DESC, seq ASC
                    LIMIT 1;
                    """,
                    (self.lane_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                    
                # Mark as running immediately
                cmd_id = row[0]
                cur.execute("UPDATE commands SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = %s", (cmd_id,))
                conn.commit()
                
                return {
                    "id": row[0],
                    "cmd_type": row[1],
                    "payload": row[2],
                    "priority": row[3],
                    "depends_on": row[4]
                }

    async def evaluate_and_reprioritize(self, current_answer: str, chunks: List[RetrievedChunk]):
        """
        Invokes the Auditor to evaluate current progress and dynamically reprioritize the queue.
        """
        auditor = AuditorAgent()
        is_ok, report = await auditor.audit(current_answer, chunks)
        
        if not is_ok:
            logger.warning(f"Auditor flagged issues: {report.get('issues')}. Escalating retrieval priorities.")
            # Promote all pending 'planner' or 'retrieval' tasks
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE commands 
                        SET priority = priority + 5 
                        WHERE lane_id = %s AND status = 'pending' 
                        AND cmd_type IN ('plan', 'llm_call');
                        """,
                        (self.lane_id,)
                    )
                conn.commit()

    def mark_completed(self, cmd_id: str, result: Dict[str, Any]):
        """Marks a command as completed, unblocking topological dependents."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commands 
                    SET status = 'done', result = %s, finished_at = CURRENT_TIMESTAMP 
                    WHERE id = %s
                    """,
                    (json.dumps(result), cmd_id)
                )
            conn.commit()
