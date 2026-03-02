"""Tests for the π₂ refinement policy (domain layer)."""

from agentic_rl_router.domain.models import RefineAction
from agentic_rl_router.domain.refinement import RefineInput, RefinementPolicy


def _inp(**kwargs) -> RefineInput:
    defaults = dict(verifier_confidence=0.5, draft_disagreement=0.5,
                    n_audit_flags=0, novelty_score=0.5, current_depth=1, current_latency_ms=500)
    defaults.update(kwargs)
    return RefineInput(**defaults)


class TestRefinementPolicy:
    def test_high_confidence_accepts(self) -> None:
        r = RefinementPolicy().decide(_inp(verifier_confidence=0.95, draft_disagreement=0.0, current_depth=2))
        assert r.action == RefineAction.ACCEPT

    def test_high_disagreement_low_depth_escalates(self) -> None:
        r = RefinementPolicy().decide(_inp(verifier_confidence=0.2, draft_disagreement=2.0, novelty_score=0.9, current_depth=0))
        assert r.action == RefineAction.ESCALATE_DEPTH

    def test_many_audit_flags_aborts(self) -> None:
        r = RefinementPolicy().decide(_inp(verifier_confidence=0.3, n_audit_flags=3, current_latency_ms=1800))
        assert r.action == RefineAction.ABORT

    def test_confidence_bounds(self) -> None:
        for c in [0.0, 0.5, 1.0]:
            r = RefinementPolicy().decide(_inp(verifier_confidence=c))
            assert 0.0 <= r.confidence <= 1.0

    def test_weight_update(self) -> None:
        p = RefinementPolicy()
        w = [1.0] * 6
        p.update_weights(w, w, w)
        assert p.get_weights()["accept"] == w
