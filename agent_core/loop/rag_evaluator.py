import logging
import time
from typing import Dict, Any, Optional
from agent_core.rag.retrieval.rl_client import RLRoutingClient

logger = logging.getLogger(__name__)

class RAGEvaluator:
    """
    Bridge between RAG results and RL feedback.
    Evaluates retrieval quality and submits metrics to the Bandit Router.
    """

    def __init__(self):
        self._rl_client = RLRoutingClient()

    async def evaluate_and_submit(
        self,
        rag_result: Dict[str, Any],
        final_answer: str,
        latency_ms: int,
        query_type: str = "analytical"
    ):
        """
        Computes a basic reward and submits feedback.
        """
        query_hash = rag_result.get("query_hash_rl")
        arm_index = rag_result.get("arm_index")

        if query_hash is None or arm_index is None:
            logger.debug("Skipping RL feedback: No routing metadata found in RAG result.")
            return

        # 1. Determine Success
        # Simple heuristic: If we have an answer and no obvious "I don't know", it's a success.
        # This could be replaced by a proper LLM-based Auditor check.
        success = True
        hallucination_flag = False
        hallucination_score = 0.0
        
        lower_answer = final_answer.lower()
        if "i don't know" in lower_answer or "no information found" in lower_answer:
            success = False
        
        # If the RAG result itself indicated a fallback or low confidence
        if rag_result.get("confidence", 1.0) < 0.3:
            success = False

        # 2. Map Auditor Score (if available)
        auditor_score = rag_result.get("confidence")

        # 3. Submit
        await self._rl_client.submit_feedback(
            query_hash=query_hash,
            arm_index=arm_index,
            success=success,
            latency_ms=latency_ms,
            hallucination_flag=hallucination_flag,
            hallucination_score=hallucination_score,
            auditor_score=auditor_score,
            depth_used=rag_result.get("depth", 0),
            query_type=query_type
        )
        logger.info(f"Submitted RL Feedback: success={success}, latency={latency_ms}ms, arm={arm_index}")
