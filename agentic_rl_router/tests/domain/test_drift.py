"""Tests for the CUSUM drift detector (domain layer)."""

from agentic_rl_router.domain.drift import CUSUMDriftDetector


class TestCUSUMDetector:
    def test_no_drift_below_threshold(self) -> None:
        d = CUSUMDriftDetector(n_arms=4, threshold=10.0, min_samples=5)
        for _ in range(10):
            result = d.update(arm=0, reward=0.5)
        assert result.drift_detected is False

    def test_detects_large_shift(self) -> None:
        d = CUSUMDriftDetector(n_arms=2, threshold=3.0, drift_sensitivity=0.01, min_samples=10)
        for _ in range(20):
            d.update(arm=0, reward=0.5)
        detected = False
        for _ in range(50):
            result = d.update(arm=0, reward=5.0)
            if result.drift_detected:
                detected = True
                break
        assert detected

    def test_reset_clears_state(self) -> None:
        d = CUSUMDriftDetector(n_arms=2)
        d.update(arm=0, reward=1.0)
        d.reset_arm(0)
        state = d.get_state(0)
        assert state is not None and state.n_samples == 0

    def test_cooldown_prevents_rapid_alarms(self) -> None:
        d = CUSUMDriftDetector(n_arms=1, threshold=0.5, drift_sensitivity=0.001, min_samples=5)
        alarms = 0
        for i in range(100):
            result = d.update(arm=0, reward=10.0 if i % 2 == 0 else -10.0)
            if result.drift_detected:
                alarms += 1
        assert alarms <= 25
