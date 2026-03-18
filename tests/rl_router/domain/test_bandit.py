"""Tests for the LinUCB contextual bandit (domain layer)."""

import numpy as np
from rl_router.domain.bandit import LinUCBBandit


def _make_bandit(d: int = 8, n_arms: int = 4, alpha: float = 1.0) -> LinUCBBandit:
    return LinUCBBandit(n_arms=n_arms, d=d, alpha=alpha, tau=0.995, viol_lambda=0.3)


class TestArmSelection:
    def test_returns_valid_arm(self) -> None:
        b = _make_bandit()
        arm, scores, _ = b.select_arm(np.random.randn(b.d))
        assert 0 <= arm < b.n_arms
        assert len(scores) == b.n_arms

    def test_all_scores_finite(self) -> None:
        b = _make_bandit()
        _, scores, _ = b.select_arm(np.random.randn(b.d))
        assert all(np.isfinite(s) for s in scores)

    def test_exploration_flag_set_initially(self) -> None:
        b = _make_bandit(d=4)
        _, _, is_expl = b.select_arm(np.ones(4))
        assert is_expl is True


class TestUpdate:
    def test_update_returns_drift_result(self) -> None:
        b = _make_bandit(d=4)
        result = b.update(arm=0, context=np.random.randn(4), reward=1.0)
        assert hasattr(result, "drift_detected")

    def test_convergence_toward_best_arm(self) -> None:
        d, b = 4, _make_bandit(d=4, n_arms=3, alpha=0.5)
        rng = np.random.default_rng(42)
        for _ in range(200):
            ctx = rng.standard_normal(d)
            for arm in range(3):
                b.update(arm=arm, context=ctx, reward=1.0 if arm == 1 else 0.0)
        _, scores, _ = b.select_arm(rng.standard_normal(d))
        assert scores[1] >= max(scores[0], scores[2]) - 0.5

    def test_violation_tracking(self) -> None:
        b = _make_bandit(d=4)
        ctx = np.random.randn(4)
        b.update(arm=0, context=ctx, reward=0.5, hallucination_flag=True)
        b.update(arm=0, context=ctx, reward=0.5, hallucination_flag=False)
        assert b.get_arm_stats(0)["violation_rate"] == 0.5


class TestReset:
    def test_soft_reset_retains_fraction(self) -> None:
        b = _make_bandit(d=4)
        for _ in range(10):
            b.update(arm=0, context=np.random.randn(4), reward=1.0)
        before = b.get_arm_stats(0)["theta_norm"]
        b.soft_reset(0, retain_fraction=0.5)
        assert b.get_arm_stats(0)["theta_norm"] < before

    def test_hard_reset_zeroes_everything(self) -> None:
        b = _make_bandit(d=4)
        b.update(arm=0, context=np.random.randn(4), reward=1.0)
        b.hard_reset()
        for a in range(b.n_arms):
            s = b.get_arm_stats(a)
            assert s["pulls"] == 0 and s["violation_rate"] == 0.0
