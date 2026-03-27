"""
The Retriever Node leveraging the Phase 1 Relational Graph search.
"""
import asyncio
import json
import urllib.request
import threading
import time
import random
import hashlib

from ..state import AgentState
from agent_core.rag.vector_store import VectorStore

def _send_feedback_async(
    query_hash: str,
    action: int,
    depth: int,
    latency_ms: int,
    success: bool,
    auditor_score: float,
    step_count: int = 1,
    invalid_call_count: int = 0,
):
    """Fire-and-forget: posts trajectory telemetry to /feedback via RLRoutingClient.

    Uses a daemon thread + asyncio.run so the retriever node is never blocked.
    step_count and invalid_call_count are forwarded so compute_differentiated_utility
    is applied by FeedbackService instead of the legacy 4-component reward.
    """
    async def _async_send():
        from agent_core.rag.retrieval.rl_client import RLRoutingClient
        client = RLRoutingClient()
        await client.submit_feedback(
            query_hash=query_hash,
            arm_index=action,
            success=success,
            latency_ms=latency_ms,
            depth_used=depth,
            auditor_score=auditor_score,
            step_count=step_count,
            invalid_call_count=invalid_call_count,
        )

    threading.Thread(target=lambda: asyncio.run(_async_send()), daemon=True).start()

def call_rl_router(query: str) -> tuple[int, int]:
    """Returns (depth, action). 10% Epsilon-Greedy exploration."""
    if random.random() < 0.10:
        depth = random.choice([0, 1, 2, 3])
        return depth, depth * 2

    url = "http://rl-router:8100/route"
    payload = {
        "query_text": query,
        "query_embedding": [0.0] * 1024
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=1.0) as f:
            resp = json.loads(f.read().decode('utf-8'))
            return resp.get("depth", 1), resp.get("action", 2)
    except Exception as e:
        print(f"[RL-Router] Routing failed: {e}")
        return 1, 2

def retrieve_context(state: AgentState) -> dict:
    """
    Looks at the latest user message and enriches the global state 
    with high-quality relational SQL chunks before the LLM thinks.
    """
    if not state.get("messages"):
        return {"relational_context": {}}

    last_msg = state["messages"][-1]
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    
    try:
        vs = VectorStore()
        
        start_time = time.time()
        # RL Router Hook (Phase D)
        depth, action = call_rl_router(query)
        query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()[:16]

        # RL Metadata for UI feedback
        rl_metadata = {
            "query_hash_rl": query_hash,
            "arm_index": action,
            "depth": depth,
            "chain_id": state.get("chain_id", 0)
        }

        
        # Multi-fidelity resolution
        k_mapping = {0: 2, 1: 5, 2: 10, 3: 15}
        limit = k_mapping.get(depth, 5)

        # Engage search
        results, _ = vs.search_skills_relational(query, limit=limit)
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Simulate Auditor
        auditor_score = 0.9 if results else 0.2
        
        # Async Update & Feedback Loop — include trajectory metrics from state
        step_count = state.get("step_count", 1) or 1
        invalid_call_count = state.get("invalid_call_count", 0) or 0
        _send_feedback_async(
            query_hash, action, depth, latency_ms, True, auditor_score,
            step_count=step_count, invalid_call_count=invalid_call_count,
        )

        return {
            "relational_context": {"sql_rag_results": results},
            "rl_metadata": rl_metadata
        }

    except Exception as e:
        print(f"[RetrieverNode] SQL-RAG failed: {e}")
        return {"relational_context": {"error": str(e)}}
