"""
Feedback use-case service.

Orchestrates: reward computation → bandit update → episode persistence.
"""

from __future__ import annotations

import numpy as np

from agentic_rl_router.domain.bandit import LinUCBBandit
from agentic_rl_router.domain.models import ToolCallLog
from agentic_rl_router.domain.reward import RewardCalculator
from agentic_rl_router.infrastructure.repositories import (
    EpisodeRepository,
    ToolExecutionRepository,
)
from agentic_rl_router.schemas.api_models import FeedbackRequest, FeedbackResponse


class FeedbackService:
    """Use-case: process feedback from the RAG pipeline."""

    def __init__(
        self,
        bandit: LinUCBBandit,
        reward_calc: RewardCalculator,
        episode_repo: EpisodeRepository,
        tool_exec_repo: ToolExecutionRepository,
    ) -> None:
        self._bandit = bandit
        self._reward = reward_calc
        self._repo = episode_repo
        self._tool_repo = tool_exec_repo

    def process_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        # 1. Map API tool calls to Domain tool calls
        domain_tool_calls = [
            ToolCallLog(
                tool_name=tc.tool_name,
                cost_tokens=tc.cost_tokens,
                execution_latency_ms=tc.execution_latency_ms,
                hallucination_type=tc.hallucination_type,
            )
            for tc in request.tool_calls
        ]

        # 2. Compute Rewards 
        # Always compute the backward-compatible 4-vector reward
        reward_vec = self._reward.compute(
            success=request.success,
            latency_ms=request.latency_ms,
            hallucination_flag=request.hallucination_flag,
            hallucination_score=request.hallucination_score,
            auditor_score=request.auditor_score,
            depth_used=request.depth_used,
            min_sufficient_depth=request.min_sufficient_depth,
        )

        # If tool_calls are provided, compute the differentiated RelyToolBench utility
        final_utility = None
        reliable_pass = False
        update_scalar = reward_vec.scalar

        if domain_tool_calls:
            final_utility = self._reward.compute_differentiated_utility(
                success=request.success,
                latency_ms=request.latency_ms,
                tool_calls=domain_tool_calls,
            )
            reliable_pass = self._reward.is_reliable_pass(
                success=request.success,
                tool_calls=domain_tool_calls,
            )
            update_scalar = final_utility

        # 3. Update bandit (zero-context fallback when full context not resent)
        dummy_context = np.zeros(self._bandit.d)
        drift_result = self._bandit.update(
            arm=request.arm_index,
            context=dummy_context,
            reward=update_scalar,
            hallucination_flag=request.hallucination_flag or (not reliable_pass and request.success),
        )

        # 4. Persist Episode
        episode_id = self._repo.log_episode(
            query_hash=request.query_hash,
            query_type=request.query_type,
            depth_used=request.depth_used,
            speculative_used=request.speculative_used,
            latency_ms=request.latency_ms,
            success=request.success,
            hallucination_flag=request.hallucination_flag,
            hallucination_score=request.hallucination_score,
            auditor_score=request.auditor_score,
            faithfulness_score=request.faithfulness_score,
            coverage_score=request.coverage_score,
            cost_tokens=request.cost_tokens,
            reward=reward_vec,
            arm_index=request.arm_index,
            final_utility_score=final_utility,
            reliable_pass_flag=reliable_pass,
        )

        # 5. Persist Tool Executions
        if domain_tool_calls:
            self._tool_repo.log_executions(episode_id, domain_tool_calls)

        return FeedbackResponse(
            episode_id=episode_id,
            reward=reward_vec,
            final_utility_score=final_utility,
            reliable_pass_flag=reliable_pass,
            drift_detected=drift_result.drift_detected,
        )
