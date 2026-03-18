"""
Pydantic v2 request/response schemas for the HTTP API.

These are the ONLY Pydantic models that know about HTTP / FastAPI.
Domain models live in domain/models.py.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from rl_router.domain.models import (
    HallucinationCategory,
    RewardVector,
    ToolCallLog,
)


# ---------------------------------------------------------------------------
# /route
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    query_text: str = Field(description="Raw query string for linguistic feature extraction")
    query_embedding: List[float] = Field(min_length=1)
    intent_logits: List[float] = Field(default_factory=lambda: [0.25, 0.25, 0.25, 0.25])
    corpus_id: Optional[str] = None
    session_id: Optional[str] = None
    difficulty_estimate: float = Field(default=0.5, ge=0.0, le=1.0)
    session_hallucination_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    previous_depth_hallucinated: bool = False


class ArmScore(BaseModel):
    arm: int
    label: str
    ucb_score: float
    mean_reward: float
    exploration_bonus: float
    violation_rate: float


class RouteResponse(BaseModel):
    action: int
    action_label: str
    depth: int
    use_speculative: bool
    is_exploration: bool
    arm_scores: List[ArmScore]


# ---------------------------------------------------------------------------
# /feedback
# ---------------------------------------------------------------------------

class ToolCallLogInput(BaseModel):
    """Per-tool-call telemetry within a feedback payload."""
    tool_name: str
    cost_tokens: int = Field(default=0, ge=0)
    execution_latency_ms: float = Field(default=0.0, ge=0.0)
    hallucination_type: HallucinationCategory = Field(
        default=HallucinationCategory.NONE
    )


class FeedbackRequest(BaseModel):
    query_hash: str
    arm_index: int = Field(ge=0, le=7)
    depth_used: int = Field(ge=0, le=3)
    speculative_used: bool = False
    latency_ms: int = Field(ge=0)
    success: bool = True
    # Legacy flat hallucination fields (still accepted)
    hallucination_flag: bool = False
    hallucination_score: float = Field(default=0.0, ge=0.0, le=1.0)
    auditor_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    faithfulness_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cost_tokens: Optional[int] = Field(default=None, ge=0)
    query_type: Optional[str] = None
    min_sufficient_depth: Optional[int] = None
    # NEW: differentiated tool-level telemetry
    tool_calls: List[ToolCallLogInput] = Field(
        default_factory=list,
        description="Per-tool invocation traces with RelyToolBench hallucination categories",
    )


class FeedbackResponse(BaseModel):
    episode_id: str
    reward: RewardVector
    final_utility_score: Optional[float] = Field(
        default=None, description="Differentiated Benefit-Cost Utility (if tool_calls provided)"
    )
    reliable_pass_flag: bool = Field(
        default=False, description="True if task succeeded with zero hallucinations (RePR)"
    )
    drift_detected: bool = False


# ---------------------------------------------------------------------------
# /refine
# ---------------------------------------------------------------------------

class RefineRequest(BaseModel):
    query_hash: str
    verifier_confidence: float = Field(ge=0.0, le=1.0)
    draft_disagreement: float = Field(default=0.0, ge=0.0)
    audit_flags: List[str] = Field(default_factory=list)
    novelty_score: float = Field(default=0.0, ge=0.0, le=1.0)
    current_depth: int = Field(ge=0, le=3)
    current_latency_ms: int = Field(ge=0)


class RefineResponse(BaseModel):
    action: int
    action_label: str
    confidence: float = Field(ge=0.0, le=1.0)
