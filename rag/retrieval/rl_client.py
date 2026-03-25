import os
import httpx
import logging
from typing import List, Optional, Dict, Any, Tuple
from rl_router.schemas.api_models import FeedbackRequest, ToolCallLogInput

logger = logging.getLogger("agentos.rag.rl_client")

# Defaults to the RL Router's port
RL_ROUTER_URL = os.environ.get("RL_ROUTER_URL", "http://localhost:8100")

class RLRoutingClient:
    """
    Client for interacting with the RL Router service.
    Supports both legacy hallucination metrics and new trajectory-level telemetry.
    """
    def __init__(self, base_url: str = RL_ROUTER_URL):
        self.base_url = base_url.rstrip("/")

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
        user_feedback: Optional[float] = None,
        # Legacy/Extra fields from agent_rag version
        hallucination_flag: bool = False,
        hallucination_score: float = 0.0,
        auditor_score: Optional[float] = None,
        query_type: str = "analytical",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submit feedback for a routing decision to the RL Router.
        """
        url = f"{self.base_url}/feedback"
        
        # Build payload compatible with rl_router.schemas.api_models.FeedbackRequest
        payload: Dict[str, Any] = {
            "query_hash": query_hash,
            "arm_index": arm_index,
            "success": success,
            "latency_ms": int(latency_ms),
            "depth_used": depth_used,
            "step_count": step_count,
            "invalid_call_count": invalid_call_count,
            "user_feedback": user_feedback,
            "hallucination_flag": hallucination_flag,
            "hallucination_score": hallucination_score,
            "auditor_score": auditor_score,
            "query_type": query_type,
        }
        
        if tool_calls:
            payload["tool_calls"] = [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in tool_calls]
            
        # Add any extra kwargs that might be expected by the schema
        payload.update(kwargs)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to submit feedback to RL Router at {url}: {e}")
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
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=5.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get routing decision from {url}: {e}")
            # Default fallback: Standard RAG (Arm 2)
            return {"action": 2, "arm_index": 2, "status": "fallback"}

    async def route(
        self, 
        query: str, 
        session_id: str, 
        query_type: str = "analytical"
    ) -> Tuple[int, bool, str, int]:
        """
        Compatibility method for legacy callers (e.g. agent_rag style).
        Note: This requires a vector store to get embeddings, normally shouldn't be here
        but kept for API compatibility during migration if needed.
        """
        logger.warning("RLRoutingClient.route is a legacy compatibility method. Use get_routing_decision.")
        # We don't have vector_store here easily without circular imports or extra dependencies
        # So we just provide a minimal stub or forward if we can.
        # Since this involves embedding, and rag/retrieval/rl_client.py didn't have it,
        # we'll just return defaults or log error.
        return 1, True, "", 1
