"""
Tree store: execution tree CRUD and ranked context building.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from .db import get_db_connection
from .models import Chain, Node, AgentRole, NodeType, NodeStatus
from .vector_store import VectorStore


class TreeStore:
    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector_store = vector_store or VectorStore()

    def create_chain(self, session_id: str, description: Optional[str] = None) -> Chain:
        """Create a new execution chain."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chains (session_id, description)
                    VALUES (%s, %s) RETURNING id, created_at;
                    """,
                    (session_id, description),
                )
                row = cur.fetchone()
                conn.commit()
                return Chain(id=row[0], session_id=session_id, description=description, created_at=row[1])

    def get_chain_by_session_id(self, session_id: str) -> Optional[Chain]:
        """Retrieve a chain by its session ID."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, session_id, description, created_at FROM chains WHERE session_id = %s ORDER BY created_at DESC LIMIT 1;",
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return Chain(id=row[0], session_id=row[1], description=row[2], created_at=row[3])

    def add_node(self, node: Node) -> Node:
        """Add a new node to the tree."""
        if node.content and not node.embedding:
            node.embedding, node.is_degraded = self.vector_store.generate_embedding(node.content)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO nodes (
                        chain_id, parent_id, agent_role, type, status, 
                        priority, planned_order, content, payload, result, embedding, deadline_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at, updated_at;
                    """,
                    (
                        node.chain_id, node.parent_id, node.agent_role.value, node.type.value, node.status.value,
                        node.priority, node.planned_order, node.content, 
                        json.dumps(node.payload) if node.payload else '{}',
                        json.dumps(node.result) if node.result else None,
                        node.embedding, node.deadline_at
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                node.id = row[0]
                node.created_at = row[1]
                node.updated_at = row[2]
                return node

    def update_node_status(self, node_id: int, status: NodeStatus, content: Optional[str] = None, result: Optional[Dict[str, Any]] = None):
        """Update node status and optionally content/embedding and result payload."""
        update_fields = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
        params = [status.value]
        
        embedding = None
        if content is not None:
            update_fields.append("content = %s")
            params.append(content)
            
            embedding, is_degraded = self.vector_store.generate_embedding(content)
            update_fields.append("embedding = %s")
            params.append(embedding)
            
            update_fields.append("is_degraded = %s")
            params.append(is_degraded)

        if result is not None:
            update_fields.append("result = %s")
            params.append(json.dumps(result))
            
        params.append(node_id)
            
        query = f"UPDATE nodes SET {', '.join(update_fields)} WHERE id = %s"
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()

    def dequeue_task(self, agent_role: AgentRole) -> Optional[Node]:
        """Atomically pop the highest priority pending task for a given agent via SKIP LOCKED."""
        from psycopg2.extras import RealDictCursor
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE nodes
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id FROM nodes
                        WHERE agent_role = %s AND status = %s
                        ORDER BY priority DESC, planned_order ASC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING *;
                    """,
                    (NodeStatus.RUNNING.value, agent_role.value, NodeStatus.PENDING.value),
                )
                row = cur.fetchone()
            conn.commit()

        if not row:
            return None

        # Reconstruct exactly like add_node would
        return Node(
            id=row["id"], chain_id=row["chain_id"], parent_id=row["parent_id"],
            agent_role=AgentRole(row["agent_role"]), type=NodeType(row["type"]),
            status=NodeStatus(row["status"]), priority=row["priority"],
            planned_order=row["planned_order"], content=row["content"],
            payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or '{}'),
            result=row["result"] if isinstance(row["result"], dict) else json.loads(row["result"]) if row["result"] else None,
            embedding=row["embedding"], deadline_at=row["deadline_at"],
            created_at=row["created_at"], updated_at=row["updated_at"]
        )

    def get_next_pending_node(self, chain_id: int) -> Optional[Node]:
        """Get the highest priority pending node for execution."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, chain_id, parent_id, agent_role, type, status, priority, 
                           planned_order, content, payload, result, embedding, deadline_at, created_at, updated_at
                    FROM nodes
                    WHERE chain_id = %s AND status = 'pending'
                    ORDER BY priority DESC, planned_order ASC, created_at ASC
                    LIMIT 1;
                    """,
                    (chain_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                
                return Node(
                    id=row[0], chain_id=row[1], parent_id=row[2], agent_role=AgentRole(row[3]),
                    type=NodeType(row[4]), status=NodeStatus(row[5]), priority=row[6],
                    planned_order=row[7], content=row[8], 
                    payload=row[9] if isinstance(row[9], dict) else json.loads(row[9] or '{}'),
                    result=row[10] if isinstance(row[10], dict) else (json.loads(row[10]) if row[10] else None),
                    embedding=row[11], deadline_at=row[12], created_at=row[13], updated_at=row[14]
                )

    def get_node_by_id(self, node_id: int) -> Optional[Node]:
        """Fetch a specific node by ID to track its execution status."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, chain_id, parent_id, agent_role, type, status, priority, 
                           planned_order, content, payload, result, embedding, deadline_at, created_at, updated_at
                    FROM nodes
                    WHERE id = %s;
                    """,
                    (node_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                    
                return Node(
                    id=row[0], chain_id=row[1], parent_id=row[2], agent_role=AgentRole(row[3]),
                    type=NodeType(row[4]), status=NodeStatus(row[5]), priority=row[6],
                    planned_order=row[7], content=row[8], 
                    payload=row[9] if isinstance(row[9], dict) else json.loads(row[9] or '{}'),
                    result=row[10] if isinstance(row[10], dict) else (json.loads(row[10]) if row[10] else None),
                    embedding=row[11], deadline_at=row[12], created_at=row[13], updated_at=row[14]
                )

    def get_node_children(self, node_id: int) -> List[Node]:
        """Get children in planned order."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, chain_id, parent_id, agent_role, type, status, priority, 
                           planned_order, content, payload, result, embedding, deadline_at, created_at, updated_at
                    FROM nodes
                    WHERE parent_id = %s
                    ORDER BY planned_order ASC;
                    """,
                    (node_id,)
                )
                rows = cur.fetchall()
                
                return [
                    Node(
                        id=r[0], chain_id=r[1], parent_id=r[2], agent_role=AgentRole(r[3]),
                        type=NodeType(r[4]), status=NodeStatus(r[5]), priority=r[6],
                        planned_order=r[7], content=r[8], 
                        payload=r[9] if isinstance(r[9], dict) else json.loads(r[9] or '{}'),
                        result=r[10] if isinstance(r[10], dict) else (json.loads(r[10]) if r[10] else None),
                        embedding=r[11], deadline_at=r[12], created_at=r[13], updated_at=r[14]
                    ) for r in rows
                ]

    def build_context(self, chain_id: int, query: str, current_node_id: Optional[int] = None, limit: int = 5) -> tuple[List[Dict[str, Any]], bool]:
        """
        Rank candidate nodes for an LLM call context window.
        Uses structural ancestors (depth), priority, and semantic similarity to query.
        Returns (candidates, is_degraded).
        """
        query_vec, is_degraded = self.vector_store.generate_embedding(query)
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if current_node_id:
                    # CTE to walk up parent_id and calculate depth factor.
                    cur.execute(
                        """
                        WITH RECURSIVE ancestors AS (
                            SELECT id, parent_id, 1 AS depth
                            FROM nodes
                            WHERE id = %s
                            UNION ALL
                            SELECT n.id, n.parent_id, a.depth + 1
                            FROM nodes n
                            INNER JOIN ancestors a ON n.id = a.parent_id
                        )
                        SELECT
                            n.id, n.parent_id, n.agent_role, n.type, n.status, n.priority, n.content,
                            1 - (n.embedding <=> %s::vector) AS sim,
                            COALESCE(1.0 / a.depth, 0) AS depth_factor
                        FROM nodes n
                        LEFT JOIN ancestors a ON n.id = a.id
                        WHERE n.chain_id = %s AND n.content IS NOT NULL
                        """,
                        (current_node_id, query_vec, chain_id)
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            n.id, n.parent_id, n.agent_role, n.type, n.status, n.priority, n.content,
                            1 - (n.embedding <=> %s::vector) AS sim,
                            0 AS depth_factor
                        FROM nodes n
                        WHERE n.chain_id = %s AND n.content IS NOT NULL
                        """,
                        (query_vec, chain_id)
                    )
                    
                rows = cur.fetchall()
                
        # Scoring logic: combination of Priority + Similarity + Depth
        w_p, w_s, w_d = 0.5, 0.3, 0.2
        candidates: List[Dict[str, Any]] = []
        for r in rows:
            nid, npid, nrole, ntype, nstatus, nprio, ncontent, sim, dfactor = r
            
            sim_val = float(sim) if sim is not None else 0.0
            prio_val = float(nprio) if nprio is not None else 5.0
            dfactor_val = float(dfactor) if dfactor is not None else 0.0
            
            score = w_p * (prio_val / 10.0) + w_s * sim_val + w_d * dfactor_val
            
            candidates.append({
                "id": nid,
                "parent_id": npid,
                "role": nrole,
                "type": ntype,
                "status": nstatus,
                "priority": nprio,
                "content": ncontent,
                "sim": sim,
                "depth_factor": dfactor,
                "score": score
            })
            
        candidates.sort(key=lambda x: x["score"], reverse=True)
        # Use a list comprehension for truncation to satisfy strict type checkers
        final_limit = int(limit)
        results = [candidates[i] for i in range(min(len(candidates), final_limit))]
        return results, is_degraded
