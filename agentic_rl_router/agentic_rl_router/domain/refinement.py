"""
π₂ Refinement Policy: second-stage adaptive controller.

Pure domain logic — no FastAPI, no DB.
Weights are injected or updated externally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from agentic_rl_router.domain.models import RefineAction


@dataclass
class RefineInput:
    """Domain-level input for the refinement decision."""

    verifier_confidence: float
    draft_disagreement: float
    n_audit_flags: int
    novelty_score: float
    current_depth: int
    current_latency_ms: int


@dataclass
class RefineOutput:
    """Domain-level output from the refinement decision."""

    action: RefineAction
    confidence: float


class RefinementPolicy:
    """Lightweight second-stage controller (π₂).

    Feature vector (6-d):
        [0] verifier_confidence
        [1] draft_disagreement (entropy)
        [2] n_audit_flags
        [3] novelty_score
        [4] depth_ratio (current/max)
        [5] latency_ratio (current_ms / budget_ms)
    """

    MAX_DEPTH: int = 3
    LATENCY_BUDGET_MS: int = 2000

    def __init__(self) -> None:
        self._w_accept = np.array(
            [1.5, -0.8, -1.5, -0.3, 0.6, -0.2], dtype=np.float64
        )
        self._w_escalate = np.array(
            [-0.8, 1.2, -0.3, 0.9, -1.2, -0.4], dtype=np.float64
        )
        self._w_abort = np.array(
            [-0.5, 0.3, 2.0, -0.2, 0.1, 0.8], dtype=np.float64
        )

    def decide(self, inp: RefineInput) -> RefineOutput:
        features = self._build_features(inp)

        scores = np.array([
            float(self._w_accept @ features),
            float(self._w_escalate @ features),
            float(self._w_abort @ features),
        ])

        exp_scores = np.exp(scores - scores.max())
        probs = exp_scores / exp_scores.sum()

        best_idx = int(np.argmax(scores))
        action = RefineAction(best_idx)

        return RefineOutput(
            action=action,
            confidence=round(float(probs[best_idx]), 4),
        )

    def update_weights(
        self,
        w_accept: List[float],
        w_escalate: List[float],
        w_abort: List[float],
    ) -> None:
        self._w_accept = np.array(w_accept, dtype=np.float64)
        self._w_escalate = np.array(w_escalate, dtype=np.float64)
        self._w_abort = np.array(w_abort, dtype=np.float64)

    def get_weights(self) -> dict:
        return {
            "accept": self._w_accept.tolist(),
            "escalate": self._w_escalate.tolist(),
            "abort": self._w_abort.tolist(),
        }

    def _build_features(self, inp: RefineInput) -> np.ndarray:
        return np.array(
            [
                inp.verifier_confidence,
                inp.draft_disagreement,
                float(inp.n_audit_flags),
                inp.novelty_score,
                inp.current_depth / self.MAX_DEPTH,
                inp.current_latency_ms / self.LATENCY_BUDGET_MS,
            ],
            dtype=np.float64,
        )
