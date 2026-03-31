"""
core/llm/routing.py
===================
RL Routing Client — hardened against timeouts, stale sockets, and feedback failures.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from core.settings import settings

logger = logging.getLogger("rl_routing")

# Separate timeouts: connect fast, allow more time for the route computation
_CONNECT_TIMEOUT = 2.0   # fail fast if the service is down
_READ_TIMEOUT    = 30.0  # Phase 7: Increased buffer for tail latencies


class RLRoutingClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize RL Routing Client.
        Defaults to settings.rl_router_url and settings.rl_router_timeout.
        """
        self.base_url = (base_url or settings.rl_router_url).rstrip("/")
        # Use per-operation timeouts instead of a single scalar
        self._timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=timeout or _READ_TIMEOUT,
            write=5.0,
            pool=5.0,
        )
        self.client = self._make_client()
        logger.info(
            "RLRoutingClient initialized (URL: %s, read_timeout: %ss)",
            self.base_url, self._timeout.read,
        )

    def _make_client(self) -> httpx.AsyncClient:
        """Always returns a fresh, open AsyncClient."""
        return httpx.AsyncClient(timeout=self._timeout)

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a live client, recreating if closed."""
        if self.client.is_closed:
            self.client = self._make_client()
            logger.debug("RLRoutingClient: recreated stale httpx client")
        return self.client

    @staticmethod
    def _arm_to_top_k(action: int | None, depth: int | None) -> int:
        if action is not None:
            mapping = {0: 0, 1: 0, 2: 5, 3: 5, 4: 10, 5: 10, 6: 20, 7: 20}
            return mapping.get(action, 5)
        depth_map = {0: 0, 1: 5, 2: 10, 3: 20}
        return depth_map.get(depth, 5)

    async def get_retrieval_action(
        self,
        query: str,
        session_id: str,
        corpus_id: str = "agentic_os_core",
        query_embedding: Optional[list] = None,
        intent_logits: Optional[list] = None,
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
            depth  = data.get("depth", 1)
            top_k  = self._arm_to_top_k(action, depth)
            speculative = bool(action is not None and action % 2 == 1)

            return {
                "action":        action,
                "arm_index":     action,       # FIX: expose as arm_index so rag_agent.py reads it correctly
                "depth":         depth,
                "top_k":         top_k,
                "speculative":   speculative,
                "query_hash_rl": data.get("query_hash_rl"),
                "raw":           data,
            }

        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            # Recreate client — stale socket, service restarted, or connection refused
            try:
                await self.client.aclose()
            except Exception:
                pass
            self.client = self._make_client()
            logger.warning(
                "RL Router connection/read failure (%s). Falling back to default depth. Client recreated.", repr(e)
            )
            return self._default_fallback(str(e))

        except Exception as e:
            try:
                await self.client.aclose()
            except Exception:
                pass
            self.client = self._make_client()
            logger.warning("RL Router routing failed: %s. Client recreated.", repr(e))
            return self._default_fallback(str(e))

    @staticmethod
    def _default_fallback(error: str) -> Dict[str, Any]:
        return {
            "action":        0, # Default to arm 0 (Collapsed Tree, Spec Off)
            "arm_index":     0,
            "depth":         0,
            "top_k":         5,
            "speculative":   False,
            "query_hash_rl": None,
            "raw":           {"fallback": True, "error": error},
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
        hallucination_flag: bool = False,
    ) -> None:
        if not query_hash:
            return  # no hash means this was a fallback call — nothing to train on
        payload = {
            "query_hash":           query_hash,
            "arm_index":            arm_index,
            "depth_used":           depth,
            "speculative_used":     speculative,
            "latency_ms":           int(latency_ms),
            "success":              success,
            "auditor_score":        reward,
            "hallucination_flag":   hallucination_flag,
        }
        try:
            # FIX: always use _get_client() so we never POST on a closed socket
            client = await self._get_client()
            await client.post(f"{self.base_url}/feedback", json=payload)
        except Exception as e:
            logger.error("Failed to submit feedback to RL Router: %s", e)

