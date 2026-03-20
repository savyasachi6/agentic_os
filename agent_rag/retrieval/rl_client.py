import httpx
import logging
import os
from typing import Dict, Any, Optional, Tuple
from agent_config import server_settings
from agent_memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

class RLRoutingClient:
    """
    Client for the RL Strategy Optimizer (Bandit) service.
    Fetches dynamic retrieval depth and speculative strategies based on query context.
    """

    def __init__(self, base_url: Optional[str] = None):
        # 1. Check if base_url is explicitly provided
        if base_url:
            self.base_url = base_url.rstrip("/")
        # 2. Check for environment variable
        elif os.getenv("RL_ROUTER_URL"):
            self.base_url = os.getenv("RL_ROUTER_URL").rstrip("/")
        # 3. Default to the gateway's mounted RL endpoint (localhost:8000/rl)
        else:
            host = server_settings.host if server_settings.host != "0.0.0.0" else "localhost"
            self.base_url = f"http://{host}:{server_settings.port}/rl"

        self._vector_store = VectorStore()

    async def route(
        self, 
        query: str, 
        session_id: str, 
        query_type: str = "analytical"
    ) -> Tuple[int, bool, str, int]:
        """
        Request a routing decision from the RL Router.
        Returns (depth, use_speculative, query_hash, arm_index).
        """
        try:
            # 1. Generate query embedding
            query_embedding, _ = await self._vector_store.generate_embedding_async(query)

            # 2. Prepare request payload
            payload = {
                "query_text": query,
                "query_embedding": query_embedding,
                "session_id": session_id,
                "query_type": query_type,
                "difficulty_estimate": 0.5, # Default, could be enriched later
                "session_hallucination_rate": 0.0,
                "previous_depth_hallucinated": False
            }

            # 3. Call RL Router API
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(f"{self.base_url}/route", json=payload)
                response.raise_for_status()
                data = response.json()

                depth = data.get("depth", 1)
                use_speculative = data.get("use_speculative", False)
                query_hash = data.get("query_hash", "")
                arm_index = data.get("action", 0)
                
                logger.info(f"RL Router Decision: depth={depth}, speculative={use_speculative} (Action: {data.get('action_label')})")
                return depth, use_speculative, query_hash, arm_index

        except Exception as e:
            logger.error(f"Failed to fetch RL routing decision: {e}. Falling back to defaults.")
            # Default fallbacks based on query type
            if query_type == "factual":
                return 0, False, "", 0
            return 1, True, "", 1 # Default speculative depth 1
            
    async def submit_feedback(
        self,
        query_hash: str,
        arm_index: int,
        success: bool,
        latency_ms: int,
        hallucination_flag: bool = False,
        hallucination_score: float = 0.0,
        auditor_score: Optional[float] = None,
        depth_used: int = 0,
        query_type: str = "analytical",
        user_feedback: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit RAG performance feedback to the RL Router to update the bandit model.
        """
        if not query_hash:
            return {"status": "skipped", "reason": "no query_hash"}

        try:
            payload = {
                "query_hash": query_hash,
                "arm_index": arm_index,
                "success": success,
                "latency_ms": latency_ms,
                "hallucination_flag": hallucination_flag,
                "hallucination_score": hallucination_score,
                "auditor_score": auditor_score,
                "depth_used": depth_used,
                "query_type": query_type,
                "user_feedback": user_feedback
            }

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(f"{self.base_url}/feedback", json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to submit RL feedback: {e}")
            return {"status": "error", "error": str(e)}
