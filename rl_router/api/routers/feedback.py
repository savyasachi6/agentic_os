"""POST /feedback — bandit update with multi-objective reward."""

from fastapi import APIRouter, Depends

from rl_router.api.dependencies import get_feedback_service
from rl_router.application.services.feedback_service import FeedbackService
from rl_router.schemas.api_models import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    request: FeedbackRequest,
    svc: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """Accept telemetry from the RAG pipeline and update the bandit."""
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(svc.process_feedback, request)
