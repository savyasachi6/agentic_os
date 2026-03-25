"""
rag/retrieval/rl_client.py
==========================
Wrapper for the RL Router API. 
Used by the gateway to submit feedback and by the retriever to get routing decisions.
"""

import os
import httpx
import logging
from typing import List, Optional, Dict, Any
from rl_router.schemas.api_models import FeedbackRequest, ToolCallLogInput

logger = logging.getLogger("agentos.rag.rl_client")

# Defaults to the RL Router's port
RL_ROUTER_URL = os.environ.get("RL_ROUTER_URL", "http://localhost:8100")

class RLRoutingClient:
    """
    Client for interacting with the RL Router service.
    """
    def __init__(self, base_url: str = RL_ROUTER_URL):
        self.base_url = base_url

    async def submit_feedback(
        self,
        query_hash: str,
        arm_index: int,
        success: bool,
        latency_ms: float = 0.0,
        depth_used: int = 0,
        step_count: int = 1,
        invalid_call_count: int = 0,
        tool_calls: Optional[List[ToolCallLogInput]] = None,
        user_feedback: float = 0.0
    ) -> Dict[str, Any]:
        """
        Submit feedback for a routing decision.
        """
        url = f"{self.base_url}/feedback"
        payload = {
            "query_hash": query_hash,
            "arm_index": arm_index,
            "success": success,
            "latency_ms": latency_ms,
            "depth_used": depth_used,
            "step_count": step_count,
            "invalid_call_count": invalid_call_count,
            "tool_calls": [tc.model_dump() for tc in (tool_calls or [])],
            "user_feedback": user_feedback
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Failed to submit feedback to RL Router: {e}")
                return {"status": "error", "message": str(e)}

    async def get_routing_decision(self, query: str, query_embedding: List[float]) -> Dict[str, Any]:
        """
        Get a routing decision (arm_index) for a query.
        """
        url = f"{self.base_url}/route"
        payload = {
            "query_text": query,
            "query_embedding": query_embedding
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=5.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Failed to get routing decision: {e}")
                # Default fallback: Standard RAG (Arm 2)
                return {"arm_index": 2, "status": "fallback"}
