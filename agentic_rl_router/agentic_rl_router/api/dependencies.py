"""
Shared FastAPI dependencies.

Constructs domain objects from infrastructure config and exposes them
as FastAPI dependencies, keeping routers thin.
"""

from __future__ import annotations

from functools import lru_cache

from agentic_rl_router.application.services.feedback_service import FeedbackService
from agentic_rl_router.application.services.routing_service import RoutingService
from agentic_rl_router.domain.bandit import LinUCBBandit
from agentic_rl_router.domain.features import ContextFeatureBuilder
from agentic_rl_router.domain.refinement import RefinementPolicy
from agentic_rl_router.domain.reward import RewardCalculator, RewardCoefficients
from agentic_rl_router.infrastructure.config import (
    bandit_settings,
    drift_settings,
    reward_settings,
)
from agentic_rl_router.infrastructure.repositories import (
    EpisodeRepository,
    ToolExecutionRepository,
)


# ---------------------------------------------------------------------------
# Singletons — built once, shared across requests
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_bandit() -> LinUCBBandit:
    return LinUCBBandit(
        n_arms=bandit_settings.n_arms,
        d=bandit_settings.context_dim,
        alpha=bandit_settings.alpha,
        tau=bandit_settings.decay_tau,
        viol_lambda=bandit_settings.violation_penalty_lambda,
        drift_threshold=drift_settings.threshold,
        drift_sensitivity=drift_settings.drift_sensitivity,
        drift_min_samples=drift_settings.min_samples_before_detection,
    )


@lru_cache(maxsize=1)
def get_reward_calculator() -> RewardCalculator:
    return RewardCalculator(
        RewardCoefficients(
            lambda_h=reward_settings.lambda_h,
            lambda_l=reward_settings.lambda_l,
            gamma=reward_settings.gamma,
            l0_ms=reward_settings.l0_ms,
            kappa=reward_settings.kappa,
            hallucination_hard_cap=reward_settings.hallucination_hard_cap,
        )
    )


@lru_cache(maxsize=1)
def get_feature_builder() -> ContextFeatureBuilder:
    return ContextFeatureBuilder()


@lru_cache(maxsize=1)
def get_refinement_policy() -> RefinementPolicy:
    return RefinementPolicy()


@lru_cache(maxsize=1)
def get_episode_repo() -> EpisodeRepository:
    return EpisodeRepository()


@lru_cache(maxsize=1)
def get_tool_exec_repo() -> ToolExecutionRepository:
    return ToolExecutionRepository()


# ---------------------------------------------------------------------------
# Application services — composed from domain + infra objects
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_routing_service() -> RoutingService:
    return RoutingService(
        bandit=get_bandit(),
        feature_builder=get_feature_builder(),
    )


@lru_cache(maxsize=1)
def get_feedback_service() -> FeedbackService:
    return FeedbackService(
        bandit=get_bandit(),
        reward_calc=get_reward_calculator(),
        episode_repo=get_episode_repo(),
        tool_exec_repo=get_tool_exec_repo(),
    )
