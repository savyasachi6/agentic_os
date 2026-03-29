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
    ) -> Dict[str, Any]:
        payload = {
            "query_text": query,
            "query_embedding": [0.0] * 1024,
            "intent_logits": [0.25, 0.25, 0.25, 0.25],
            "difficulty_estimate": 0.5,
            "session_hallucination_rate": 0.0,
            "previous_depth_hallucinated": False,
            "session_id": session_id,
            "corpus_id": corpus_id,
        }

        try:
            resp = await self.client.post(f"{self.base_url}/route", json=payload)
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
            logger.warning(f"RL Router routing failed: {e}. Falling back to default depth.")
            return {
                "action": 2,
                "depth": 1,
                "top_k": 5,
                "speculative": False,
                "query_hash_rl": None,
                "raw": {"fallback": True, "error": str(e)},
            }

    async def submit_feedback(self, query_hash: str, reward: float) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(
                    f"{self.base_url}/feedback/system",
                    json={"query_hash_rl": query_hash, "reward": reward},
                )
        except Exception as e:
            logger.error(f"Failed to submit systematic feedback: {e}")
