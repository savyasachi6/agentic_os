"""POST /refine — π₂ second-stage refinement."""

from fastapi import APIRouter, Depends

from rl_router.api.dependencies import get_refinement_policy
from rl_router.domain.refinement import RefineInput, RefinementPolicy
from rl_router.schemas.api_models import RefineRequest, RefineResponse

router = APIRouter()


@router.post("/refine", response_model=RefineResponse)
async def refine(
    request: RefineRequest,
    policy: RefinementPolicy = Depends(get_refinement_policy),
) -> RefineResponse:
    """Mid-episode refinement: accept, escalate, or abort."""
    inp = RefineInput(
        verifier_confidence=request.verifier_confidence,
        draft_disagreement=request.draft_disagreement,
        n_audit_flags=len(request.audit_flags),
        novelty_score=request.novelty_score,
        current_depth=request.current_depth,
        current_latency_ms=request.current_latency_ms,
    )
    result = policy.decide(inp)
    return RefineResponse(
        action=result.action.value,
        action_label=result.action.name.lower(),
        confidence=result.confidence,
    )
