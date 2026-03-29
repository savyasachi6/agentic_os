"""Debug and observability endpoints for the RL Router."""

from fastapi import APIRouter, Depends
from typing import Dict, Any

from rl_router.api.dependencies import get_bandit, get_episode_repo, get_feedback_service
from rl_router.domain.bandit import LinUCBBandit
from rl_router.infrastructure.repositories import EpisodeRepository
from rl_router.application.services.feedback_service import FeedbackService
from rl_router.infrastructure.context_cache import context_registry
import numpy as np

router = APIRouter()

@router.post("/bandit/replay")
async def replay_bandit(
    limit: int = 1000,
    bandit: LinUCBBandit = Depends(get_bandit),
    episode_repo: EpisodeRepository = Depends(get_episode_repo),
) -> Dict[str, Any]:
    """
    Re-train the bandit from the most recent episodes.
    Useful for 'Train' button in UI.
    """
    episodes = episode_repo.get_recent_episodes(limit=limit)
    count = 0
    
    for ep in episodes:
        # Reconstruct context from stored vector or zeros
        context = ep.get("context_vector")
        if context is None:
            context = np.zeros(bandit.d)
        else:
            context = np.array(context)

        # Update bandit with the scalar reward logged during the episode
        reward_scalar = ep.get("reward_scalar")
        if reward_scalar is not None:
            bandit.update(
                arm=ep["arm_index"],
                context=context,
                reward=float(reward_scalar),
                hallucination_flag=bool(ep.get("hallucination_flag", False))
            )
            count += 1

    return {"status": "success", "trained_on": count}

@router.get("/bandit/stats")
async def get_bandit_stats(
    bandit: LinUCBBandit = Depends(get_bandit)
) -> Dict[str, Any]:
    """Return real-time metrics for the RL agent."""
    arm_stats = bandit.get_all_arm_stats()
    
    return {
        "n_arms": bandit.n_arms,
        "d": bandit.d,
        "alpha": bandit.alpha,
        "arm_stats": arm_stats,
        "registry": {
            "size": context_registry.size,
            "feedback_rate": context_registry.feedback_rate,
            "total_evictions": context_registry.total_evictions,
            "ttl_config": context_registry._ttl,
            "maxsize_config": context_registry._maxsize
        }
    }
