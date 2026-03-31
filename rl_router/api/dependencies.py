"""
Shared FastAPI dependencies.

Constructs domain objects from infrastructure config and exposes them
as FastAPI dependencies, keeping routers thin.
"""

from __future__ import annotations

from typing import Optional, Any, Dict, List
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
# Singletons — built once, shared across requests (Hardened)
# ---------------------------------------------------------------------------

_BANDIT: Optional[LinUCBBandit] = None
_ROUTING_SERVICE: Optional[RoutingService] = None
_BANDIT_REPO: Optional[BanditRepository] = None
_FEATURE_BUILDER: Optional[ContextFeatureBuilder] = None


def get_bandit_repo() -> BanditRepository:
    global _BANDIT_REPO
    if _BANDIT_REPO is None:
        _BANDIT_REPO = BanditRepository()
    return _BANDIT_REPO


def get_feature_builder() -> ContextFeatureBuilder:
    global _FEATURE_BUILDER
    if _FEATURE_BUILDER is None:
        _FEATURE_BUILDER = ContextFeatureBuilder()
    return _FEATURE_BUILDER


def get_bandit() -> LinUCBBandit:
    """Singleton getter for the LinUCB Bandit. Hardened with Global Singleton."""
    global _BANDIT
    if _BANDIT is not None:
        return _BANDIT

    _BANDIT = LinUCBBandit(
        n_arms=bandit_settings.n_arms,
        d=bandit_settings.context_dim,
        alpha=bandit_settings.alpha,
        tau=bandit_settings.decay_tau,
        viol_lambda=bandit_settings.violation_penalty_lambda,
        drift_threshold=drift_settings.threshold,
        drift_sensitivity=drift_settings.drift_sensitivity,
        drift_min_samples=drift_settings.min_samples_before_detection,
    )
    
    # 1. Try loading from Database (Fast Fallback)
    try:
        repo = get_bandit_repo()
        # Non-blocking check for weights
        db_weights = repo.load_weights("linucb_rag_depth")
        if db_weights:
            _BANDIT.load_from_bytes(db_weights)
            print("[bandit] Successfully loaded weights from Database")
            return _BANDIT
    except Exception as e:
        print(f"[bandit] Database weight loading skipped/failed: {e}")

    # 2. Fallback to Local migration file
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    weights_path = os.path.join(pkg_root, "bandit_weights.npz")
    
    if os.path.exists(weights_path):
        try:
            with open(weights_path, "rb") as f:
                _BANDIT.load_from_bytes(f.read())
            print(f"[bandit] Loaded weights from fallback file: {weights_path}")
            return _BANDIT
        except Exception as e:
            print(f"[bandit] Local file loading failed: {e}")

    print("[bandit] No existing weights found. Starting with fresh coefficients.")
    return _BANDIT


def bootstrap_bandit(bandit: LinUCBBandit):
    """
    Perform Heuristic Warm-Starting (Cold Start Bootstrapping).
    This is slow (~15s) and should be run in a background task.
    """
    print("[bandit] Performing Heuristic Warm-Start (Cold Start)...")
    try:
        from rl_router.utils.bootstrapper import Teacher
        from rl_router.domain.features import ContextFeatureBuilder
        from rl_router.domain.models import RetrievalAction
        
        queries = [
            "how to refactor the agent_core loop",
            "debug the routing service",
            "link the new API to the UI",
            "hi",
            "what is the meaning of life?",
            "kubernetes throughput issues",
        ]
        fb = ContextFeatureBuilder()
        for q in queries:
            depth, reward = Teacher.evaluate_query(q)
            if depth > 3:
                depth = 3
            action = RetrievalAction.from_components(depth=depth, speculative=False).value
            zeroed_embedding = [0.0] * bandit.d
            ctx = fb.build(
                query_text=q,
                query_embedding=zeroed_embedding,
            )
            bandit.update(action, ctx, float(reward), hallucination_flag=False)
        print("[bandit] Heuristic Warm-Start Complete.")
    except Exception as e:
        print(f"[bandit] Bootstrapping failed: {e}")
            
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

def get_routing_service() -> RoutingService:
    global _ROUTING_SERVICE
    if _ROUTING_SERVICE is None:
        _ROUTING_SERVICE = RoutingService(
            bandit=get_bandit(),
            feature_builder=get_feature_builder(),
        )
    return _ROUTING_SERVICE


@lru_cache(maxsize=1)
def get_feedback_service() -> FeedbackService:
    return FeedbackService(
        bandit=get_bandit(),
        reward_calc=get_reward_calculator(),
        episode_repo=get_episode_repo(),
        tool_exec_repo=get_tool_exec_repo(),
    )
