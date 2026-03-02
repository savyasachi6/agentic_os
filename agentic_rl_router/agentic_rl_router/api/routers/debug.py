"""GET /debug/thought-trace — telemetry inspection endpoint."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from agentic_rl_router.api.dependencies import get_bandit, get_episode_repo
from agentic_rl_router.domain.bandit import LinUCBBandit
from agentic_rl_router.infrastructure.repositories import EpisodeRepository

router = APIRouter()


@router.get("/debug/thought-trace")
async def thought_trace(
    query_hash: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    repo: EpisodeRepository = Depends(get_episode_repo),
    bandit: LinUCBBandit = Depends(get_bandit),
) -> Dict[str, Any]:
    """Debug: recent retrieval episodes and arm diagnostics."""
    episodes = repo.get_recent_episodes(query_hash=query_hash, limit=limit)
    arm_stats = bandit.get_all_arm_stats()
    return {"episodes": episodes, "arm_stats": arm_stats}
