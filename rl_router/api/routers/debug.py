"""Debug and observability endpoints for the RL Router."""

from fastapi import APIRouter, Depends
from typing import Dict, Any

from rl_router.api.dependencies import get_bandit
from rl_router.domain.bandit import LinUCBBandit
from rl_router.infrastructure.context_cache import context_registry

router = APIRouter()

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
