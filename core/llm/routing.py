import logging
from typing import Any, Dict, Optional

import httpx

from core.settings import settings

logger = logging.getLogger("rl_routing")


class RLRoutingClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize RL Routing Client.
        Defaults to settings.rl_router_url and settings.rl_router_timeout.
        """
        self.base_url = (base_url or settings.rl_router_url).rstrip("/")
        self.timeout = timeout or settings.rl_router_timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)
        logger.info(f"RLRoutingClient initialized (URL: {self.base_url}, Timeout: {self.timeout}s)")

    async def _get_client(self) -> httpx.AsyncClient:
        """Helper to ensure a fresh, non-stale client is used if needed."""
        # Check if client is closed or we just want to ensure freshness
        if self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        return self.client

    @staticmethod
    def _arm_to_top_k(action: int | None, depth: int | None) -> int:
        if action is not None:
            if action in (0, 1):
                return 0
            if action in (2, 3):
                return 5
            if action in (4, 5):
                return 10
            if action in (6, 7):
                return 20
        depth_map = {0: 0, 1: 5, 2: 10, 3: 20}
        return depth_map.get(depth, 5)

    async def get_retrieval_action(
        self,
        query: str,
        session_id: str,
        corpus_id: str = "agentic_os_core",
        query_embedding: Optional[list[float]] = None,
        intent_logits: Optional[list[float]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "query_text": query,
            "query_embedding": query_embedding or ([0.0] * 1024),
            "intent_logits": intent_logits or [0.25, 0.25, 0.25, 0.25],
            "difficulty_estimate": 0.5,
            "session_hallucination_rate": 0.0,
            "previous_depth_hallucinated": False,
            "session_id": session_id,
            "corpus_id": corpus_id,
        }

        try:
            client = await self._get_client()
            resp = await client.post(f"{self.base_url}/route", json=payload)
            resp.raise_for_status()
            data = resp.json()

            action = data.get("action")
            depth = data.get("depth", 1)
            top_k = self._arm_to_top_k(action, depth)
            
            # Policy: Odd-numbered arms (1, 3, 5, 7) are speculative.
            # (Ensures implementation matches design even if router sends mismatched fields)
            speculative = bool(action is not None and action % 2 == 1)

            return {
                "action": action,
                "depth": depth,
                "top_k": top_k,
                "speculative": speculative,
                "query_hash_rl": data.get("query_hash_rl"),
                "raw": data,
            }
        except Exception as e:
            # FORCE RECREATION of client on next try to solve DNS/Stale-Socket issues
            await self.client.aclose()
            logger.warning(f"RL Router routing failed: {repr(e)}. Falling back to default depth. Client Reset.")
            return {
                "action": 0, # Default to arm 0 (Collapsed Tree, Spec Off)
                "depth": 0,
                "top_k": 5, # Fallback to 5 chunks for RAG resilience
                "speculative": False,
                "query_hash_rl": None,
                "raw": {"fallback": True, "error": str(e), "type": str(type(e))},
            }

    async def submit_feedback(
        self,
        query_hash: str,
        reward: float,
        arm_index: int = 2,
        depth: int = 1,
        speculative: bool = False,
        latency_ms: int = 0,
        success: bool = True,
    ) -> None:
        payload = {
            "query_hash": query_hash,
            "arm_index": arm_index,
            "depth_used": depth,
            "speculative_used": speculative,
            "latency_ms": int(latency_ms),
            "success": success,
            "auditor_score": reward,  # Mapping scalar reward to auditor_score for utility calculation
        }
        try:
            await self.client.post(
                f"{self.base_url}/feedback",
                json=payload,
            )
        except Exception as e:
            logger.error(f"Failed to submit feedback to RL Router: {e}")
