"""GET /health — liveness probe."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from rl_router.api.dependencies import get_bandit
from rl_router.domain.bandit import LinUCBBandit

router = APIRouter()


@router.get("/health")
async def health(
    bandit: LinUCBBandit = Depends(get_bandit),
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "rl_router",
        "bandit_arms": bandit.n_arms,
    }
