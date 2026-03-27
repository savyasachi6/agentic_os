"""
training/curriculum.py
======================
Curriculum Agent for autonomous background RL rollouts.
Implements ADPO (Ambiguity Dynamic Policy Optimization) via self-consistency.
"""

import os
import sys
import asyncio
import random
import hashlib
import logging
import numpy as np
from typing import List, Dict, Any, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.rag.retrieval.rl_client import RLRoutingClient
from rl_router.schemas.api_models import ToolCallLogInput
from rl_router.domain.models import HallucinationCategory

logger = logging.getLogger("agentos.training.curriculum")
logging.basicConfig(level=logging.INFO)

# --- Synthetic Task Generation ---

QUERY_TYPES = {
    "factual": [
        "What is the capital of Japan?",
        "How many planets are in the solar system?",
        "Who wrote the Great Gatsby?",
        "What is the boiling point of nitrogen?",
        "Define quantum entanglement."
    ],
    "analytical": [
        "Compare the performance of pgvector Ivfflat vs HNSW.",
        "What are the trade-offs of using GraphQL over REST for agentic systems?",
        "Explain the impact of context window size on RAG faithfulness.",
        "Evaluate different prompt engineering techniques for planning agents."
    ],
    "multi_hop": [
        "How does the CEO of the company that acquired Slack in 2021 relate to the founder of Salesforce?",
        "What is the connection between the architect of the Burj Khalifa and the Sears Tower?",
        "If a person lives in the city where the 2024 Olympics are held, what is the local time there now?",
        "Find the relation between the developer of LangChain and the creator of LangGraph."
    ]
}

class CurriculumAgent:
    """
    Autonomously generates tasks and runs rollouts to train the RL router.
    Implements ADPO via multiple rollouts per task.
    """
    def __init__(self, n_rollouts: int = 3):
        self.agent = CoordinatorAgent()
        self.rl_client = RLRoutingClient()
        self.n_rollouts = n_rollouts

    async def generate_task(self) -> Tuple[str, str]:
        """Randomly sample a query and its type."""
        q_type = random.choice(list(QUERY_TYPES.keys()))
        query = random.choice(QUERY_TYPES[q_type])
        return query, q_type

    async def run_adpo_rollout(self, query: str, q_type: str):
        """
        Run N rollouts for the same query. 
        Calculate self-consistency and submit weighted feedback.
        """
        rollouts = []
        for i in range(self.n_rollouts):
            logger.info(f"  Rollout {i+1}/{self.n_rollouts} for: {query[:50]}...")
            
            # 1. Run the turn
            response = await self.agent.run_turn(query)
            metrics = self.agent.last_run_metrics
            
            # 2. Capture trajectory data
            # In a real setup, we'd also capture the arm_index chosen by the router.
            # RLRoutingClient doesn't expose the last action easily; we'd need to intercept it.
            # For simulation, we'll assume the router is active and we just need the query_hash.
            query_hash = hashlib.md5(query.encode()).hexdigest()
            
            rollouts.append({
                "response": response,
                "metrics": metrics,
                "query_hash": query_hash
            })

        # 3. ADPO: Consistency Check
        # If responses vary wildly, it's an "ambiguous" task.
        # We'll use a simple string similarity or just exact match for now.
        responses = [r["response"] for r in rollouts]
        consistency_score = len(set(responses)) / self.n_rollouts # 1.0 means all different, lower is better? 
        # Actually consistency = (matching pairs) / total.
        # Let's say: weight = percentage of most common response.
        from collections import Counter
        counts = Counter(responses)
        most_common_count = counts.most_common(1)[0][1]
        weight = most_common_count / self.n_rollouts
        
        logger.info(f"  ADPO Consistency Weight: {weight:.2f}")

        # 4. Submit Feedback for each rollout
        for r in rollouts:
            success = "Error" not in r["response"] and len(r["response"]) > 10
            
            # Map guard_log to ToolCallLogInput
            tool_calls = []
            for entry in r["metrics"].get("guard_log", []):
                tool_calls.append(ToolCallLogInput(
                    tool_name=entry["agent"],
                    cost_tokens=1000, # Mocked
                    execution_latency_ms=100.0,
                    hallucination_type=HallucinationCategory.NONE
                ))

            # Actually submit to RL Router
            # Note: We need the arm_index. In a production rollout, 
            # the router returns this. Here we'll assume arm 2 (Standard RAG) for now
            # or extract it if we modify the router client to store it.
            try:
                await self.rl_client.submit_feedback(
                    query_hash=r["query_hash"],
                    arm_index=2, # Placeholder
                    success=success,
                    latency_ms=500,
                    depth_used=1,
                    step_count=r["metrics"]["step_count"],
                    invalid_call_count=r["metrics"]["invalid_call_count"],
                    tool_calls=tool_calls,
                    user_feedback=int(weight > 0.6) # Surrogate user feedback from consistency
                )
            except Exception as e:
                logger.error(f"Failed to submit feedback: {e}")

    async def start_training(self, episodes: int = 10):
        logger.info(f"Starting Curriculum Training for {episodes} episodes...")
        for i in range(episodes):
            logger.info(f"Episode {i+1}/{episodes}")
            query, q_type = await self.generate_task()
            await self.run_adpo_rollout(query, q_type)
            await asyncio.sleep(1)

if __name__ == "__main__":
    curriculum = CurriculumAgent(n_rollouts=2)
    asyncio.run(curriculum.start_training(episodes=5))
