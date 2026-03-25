"""
Multi-objective reward calculator with non-linear scalarisation
and differentiated Benefit-Cost Utility (RelyToolBench).

Pure domain logic — no FastAPI, no DB, no config singletons.
Coefficients are injected via RewardCoefficients dataclass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from rl_router.domain.models import (
    HallucinationCategory,
    RewardVector,
    ToolCallLog,
)


# ---------------------------------------------------------------------------
# Differentiated hallucination penalties (RelyToolBench taxonomy)
# ---------------------------------------------------------------------------

DEFAULT_HALLUCINATION_PENALTIES: Dict[HallucinationCategory, float] = {
    HallucinationCategory.NONE: 0.0,
    HallucinationCategory.FORMAT: 0.5,    # Recoverable via retry loop
    HallucinationCategory.TIMING: 1.0,    # Wasted API call / unnecessary tool use
    HallucinationCategory.TYPE: 2.0,      # Chose a completely irrelevant tool
    HallucinationCategory.CONTENT: 4.0,   # Fatal: fabricated data or parameters
}


@dataclass(frozen=True)
class RewardCoefficients:
    """Snapshot of reward hyperparameters (injectable, testable)."""

    lambda_h: float = 0.8
    lambda_l: float = 0.1
    gamma: float = 0.15
    l0_ms: float = 250.0
    kappa: float = 2.0
    hallucination_hard_cap: float = -0.3
    lambda_tool_cost: float = 1e-4
    lambda_feedback: float = 0.5
    hallucination_penalties: Dict[HallucinationCategory, float] = field(
        default_factory=lambda: dict(DEFAULT_HALLUCINATION_PENALTIES)
    )
    # Refined Reward Coefficients (Agent-R1 / Verlog inspired)
    alpha_success: float = 1.0
    beta_step: float = 0.05
    gamma_invalid: float = 0.2
    gamma_step: float = 0.95    # Step-level discount
    gamma_token: float = 0.99   # Token-level discount (Dual Discounting)


class RewardCalculator:
    """Computes multi-objective reward vectors and scalarises them.

    Supports two modes:
      1. ``compute()`` — the original 4-component reward (backward compat)
      2. ``compute_differentiated_utility()`` — Benefit-Cost Utility
         with granular RelyToolBench hallucination penalties.

    Hallucination safety dominates: any detected hallucination hard-caps
    the utility regardless of latency or quality improvements.
    """

    def __init__(self, coefficients: RewardCoefficients | None = None) -> None:
        self._c = coefficients or RewardCoefficients()

    # ------------------------------------------------------------------
    # Legacy 4-component reward (kept for backward compatibility)
    # ------------------------------------------------------------------

    def compute(
        self,
        *,
        success: bool,
        latency_ms: int,
        hallucination_flag: bool,
        hallucination_score: float = 0.0,
        auditor_score: float | None = None,
        depth_used: int = 0,
        min_sufficient_depth: int | None = None,
        user_feedback: float | None = None,
    ) -> RewardVector:
        """Compute the full reward vector and its scalar utility."""

        # r1 — quality
        quality = auditor_score if auditor_score is not None else float(success)

        # r2 — hallucination penalty (always ≤ 0)
        raw_h = min(1.0, self._c.kappa * hallucination_score) if hallucination_score > 0 else 0.0
        if hallucination_flag and raw_h == 0.0:
            raw_h = 1.0
        hallucination_penalty = -self._c.lambda_h * raw_h

        # r3 — log-smoothed latency cost (always ≤ 0)
        latency_cost = -self._c.lambda_l * math.log1p(latency_ms / self._c.l0_ms)

        # r4 — over-thinking penalty (always ≤ 0)
        if min_sufficient_depth is not None:
            excess = max(0, depth_used - min_sufficient_depth)
        else:
            excess = 0
        overthinking_penalty = -self._c.gamma * excess

        # r5 — explicit user feedback (reward boost or penalty)
        feedback_reward = self._c.lambda_feedback * float(user_feedback or 0.0)

        scalar = self._scalarise(
            quality=quality + feedback_reward,
            hallucination_penalty=hallucination_penalty,
            latency_cost=latency_cost,
            overthinking_penalty=overthinking_penalty,
            hallucination_detected=hallucination_flag or hallucination_score > 0.0,
        )

        return RewardVector(
            quality=float(round(float(quality), 6)),
            hallucination_penalty=float(round(float(hallucination_penalty), 6)),
            latency_cost=float(round(float(latency_cost), 6)),
            overthinking_penalty=float(round(float(overthinking_penalty), 6)),
            scalar=float(round(float(scalar), 6)),
        )

    # ------------------------------------------------------------------
    # Differentiated Benefit-Cost Utility (RelyToolBench)
    # ------------------------------------------------------------------

    def compute_differentiated_utility(
        self,
        *,
        success: bool,
        latency_ms: float,
        step_count: int = 1,
        invalid_call_count: int = 0,
        tool_calls: List[ToolCallLog] | None = None,
        user_feedback: float | None = None,
    ) -> float:
        """Compute Benefit-Cost Utility with granular trajectory metrics.

        Formula (Refined):
            R = α*I(success) - β*T - γ*Σ(invalid) - P_tool + R_feedback + C_latency

        Dual Discounting GAE logic:
            Separates step-level discounting from token-level discounting.
        """
        tool_calls = tool_calls or []

        # 1. Success Reward
        r_success = self._c.alpha_success if success else -self._c.alpha_success

        # 2. Step Penalty (T)
        p_step = self._c.beta_step * step_count

        # 3. Invalid Call Penalty (γ)
        p_invalid = self._c.gamma_invalid * invalid_call_count

        # 4. Tool / Token Cost (Dual Discounting flavor: γ_token)
        total_tokens = sum(tc.cost_tokens for tc in tool_calls)
        p_tool = total_tokens * self._c.lambda_tool_cost
        
        # Apply Dual Discounting (Simplified for single-turn update: token-level decay)
        # We weight the tool cost by its own discount factor relative to token volume
        p_tool *= (self._c.gamma_token ** (total_tokens / 100.0)) # Heuristic

        # 5. Latency penalty (Legacy λ_l * log(1+L))
        c_l = self._c.lambda_l * math.log1p(latency_ms / self._c.l0_ms)

        # 6. User feedback reward
        r_feedback = self._c.lambda_feedback * float(user_feedback or 0.0)

        utility = r_success - p_step - p_invalid - p_tool - c_l + r_feedback
        return float(round(float(utility), 6))

    def is_reliable_pass(self, success: bool, tool_calls: List[ToolCallLog] | None = None) -> bool:
        """True only if task succeeded with zero hallucinations (RePR metric)."""
        if not success:
            return False
        for tc in (tool_calls or []):
            if tc.hallucination_type != HallucinationCategory.NONE:
                return False
        return True

    # ------------------------------------------------------------------
    # Scalarisation (internal)
    # ------------------------------------------------------------------

    def _scalarise(
        self,
        *,
        quality: float,
        hallucination_penalty: float,
        latency_cost: float,
        overthinking_penalty: float,
        hallucination_detected: bool,
    ) -> float:
        """Non-linear scalarisation enforcing hallucination safety dominance."""
        raw = quality + hallucination_penalty + latency_cost + overthinking_penalty
        if hallucination_detected:
            return min(raw, self._c.hallucination_hard_cap)
        return raw
