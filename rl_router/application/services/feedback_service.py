"""
Feedback use-case service.

Orchestrates: reward computation → bandit update → episode persistence.
"""

from __future__ import annotations

import numpy as np

from rl_router.domain.bandit import LinUCBBandit
from rl_router.domain.models import ToolCallLog
from rl_router.domain.reward import RewardCalculator
from rl_router.infrastructure.repositories import (
    EpisodeRepository,
    ToolExecutionRepository,
)
from rl_router.schemas.api_models import FeedbackRequest, FeedbackResponse
from rl_router.infrastructure.context_cache import context_registry


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
        # 0. Log incoming telemetry for observability
        import logging
        logger = logging.getLogger("rl_router.feedback")
        logger.info(
            f"Processing feedback: query_hash={request.query_hash}, arm={request.arm_index}, "
            f"success={request.success}, latency={request.latency_ms}ms, "
            f"steps={request.step_count}, invalid_calls={request.invalid_call_count}, "
            f"query_type={request.query_type}"
        )
        if request.tool_calls:
            logger.info(f"Feedback includes {len(request.tool_calls)} tool calls")

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
            user_feedback=request.user_feedback,
        )

        # Defaults — overridden below if trajectory metrics are present.
        final_utility: float | None = None
        reliable_pass: bool = False
        update_scalar: float = reward_vec.scalar

        # If tool_calls are provided OR trajectory metrics show multi-step work,
        # compute the differentiated Benefit-Cost Utility and use it as the bandit update.
        # Previously this was gated on `domain_tool_calls` only — meaning step_count and
        # invalid_call_count were silently ignored for all normal retriever feedback.
        use_trajectory_reward = (
            bool(domain_tool_calls)
            or request.step_count > 1
            or request.invalid_call_count > 0
        )
        if use_trajectory_reward:
            final_utility = self._reward.compute_differentiated_utility(
                success=request.success,
                latency_ms=request.latency_ms,
                step_count=request.step_count,
                invalid_call_count=request.invalid_call_count,
                tool_calls=domain_tool_calls,
                user_feedback=request.user_feedback,
            )
            reliable_pass = self._reward.is_reliable_pass(
                success=request.success,
                tool_calls=domain_tool_calls,
            )
            update_scalar = final_utility

        # 3. Update bandit (Phase 3: Use cached context if available)
        context = context_registry.pop(request.query_hash) # Use pop to clean up
        if context is None:
            # Fallback to zero context if cache expired or missing
            context = np.zeros(self._bandit.d)
        
        drift_result = self._bandit.update(
            arm=request.arm_index,
            context=context,
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
            context_vector=context.tolist() if isinstance(context, np.ndarray) else context,
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
