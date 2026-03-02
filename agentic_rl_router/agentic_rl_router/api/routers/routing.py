"""POST /route — π₁ bandit arm selection."""

from fastapi import APIRouter, Depends

from agentic_rl_router.api.dependencies import get_routing_service
from agentic_rl_router.application.services.routing_service import RoutingService
from agentic_rl_router.schemas.api_models import RouteRequest, RouteResponse

router = APIRouter()


@router.post("/route", response_model=RouteResponse)
async def route(
    request: RouteRequest,
    svc: RoutingService = Depends(get_routing_service),
) -> RouteResponse:
    """Select the optimal retrieval depth and speculative strategy."""
    return svc.route(request)
