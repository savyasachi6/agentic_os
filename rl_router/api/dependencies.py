"""
Shared FastAPI dependencies.

Constructs domain objects from infrastructure config and exposes them
as FastAPI dependencies, keeping routers thin.
"""

from __future__ import annotations

import os
from functools import lru_cache

from rl_router.application.services.feedback_service import FeedbackService
from rl_router.application.services.routing_service import RoutingService
from rl_router.domain.bandit import LinUCBBandit
from rl_router.domain.features import ContextFeatureBuilder
from rl_router.domain.refinement import RefinementPolicy
from rl_router.domain.reward import RewardCalculator, RewardCoefficients
from rl_router.infrastructure.config import (
    bandit_settings,
    drift_settings,
    reward_settings,
)
from rl_router.infrastructure.repositories import (
    EpisodeRepository,
    ToolExecutionRepository,
    BanditRepository,
)


# ---------------------------------------------------------------------------
# Singletons — built once, shared across requests
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_bandit() -> LinUCBBandit:
    bandit = LinUCBBandit(
        n_arms=bandit_settings.n_arms,
        d=bandit_settings.context_dim,
        alpha=bandit_settings.alpha,
        tau=bandit_settings.decay_tau,
        viol_lambda=bandit_settings.violation_penalty_lambda,
        drift_threshold=drift_settings.threshold,
        drift_sensitivity=drift_settings.drift_sensitivity,
        drift_min_samples=drift_settings.min_samples_before_detection,
    )
    
    # Warmer Start — Try loading from DB first (most recent)
    repo = get_bandit_repo()
    db_weights = repo.load_weights("linucb_rag_depth")
    
    if db_weights:
        try:
            bandit.load_from_bytes(db_weights)
            print("[bandit] Loaded weights from Database")
            return bandit
        except Exception as e:
            print(f"[bandit] Failed to load weights from DB: {e}")

    # Fallback to local file (Cold Start / Migration)
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    weights_path = os.path.join(pkg_root, "bandit_weights.npz")
    
    if os.path.exists(weights_path):
        try:
            with open(weights_path, "rb") as f:
                bandit.load_from_bytes(f.read())
            print(f"[bandit] Loaded weights from {weights_path}")
        except Exception as e:
            print(f"[bandit] Failed to load weights from file: {e}")
            
    return bandit


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


@lru_cache(maxsize=1)
def get_bandit_repo() -> BanditRepository:
    return BanditRepository()


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
