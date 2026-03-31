"""GET /health — liveness probe."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from rl_router.api.dependencies import get_bandit
from rl_router.domain.bandit import LinUCBBandit

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.get("/health")
async def health(request: Request):
    # Workers use /health for readiness. Only return 200 when initialized.
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Bandit not yet initialized")
    return {"status": "ok", "service": "rl-router"}
