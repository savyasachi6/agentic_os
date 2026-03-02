"""
CUSUM drift detector for non-stationary bandit environments.

Pure domain logic — no config singletons.
Thresholds are injected at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ArmDriftState:
    """Per-arm CUSUM accumulators and statistics."""

    n_samples: int = 0
    reward_sum: float = 0.0
    cusum_pos: float = 0.0
    cusum_neg: float = 0.0
    last_alarm_at: int = 0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.n_samples if self.n_samples > 0 else 0.0


@dataclass
class DriftResult:
    """Result of a drift check."""

    drift_detected: bool
    arm: int
    cusum_value: float
    mean_reward: float
    n_samples: int


class CUSUMDriftDetector:
    """Monitors per-arm reward streams for distribution shifts."""

    def __init__(
        self,
        n_arms: int = 8,
        threshold: float = 5.0,
        drift_sensitivity: float = 0.05,
        min_samples: int = 30,
    ) -> None:
        self._n_arms = n_arms
        self._threshold = threshold
        self._delta = drift_sensitivity
        self._min_samples = min_samples
        self._arms: Dict[int, ArmDriftState] = {
            i: ArmDriftState() for i in range(n_arms)
        }

    def update(self, arm: int, reward: float) -> DriftResult:
        """Feed a new reward observation. Returns drift detection result."""
        state = self._arms[arm]
        state.n_samples += 1
        state.reward_sum += reward

        mu = state.mean_reward
        state.cusum_pos = max(0.0, state.cusum_pos + (reward - mu - self._delta))
        state.cusum_neg = max(0.0, state.cusum_neg - (reward - mu + self._delta))

        cusum_val = max(state.cusum_pos, state.cusum_neg)

        drift = (
            cusum_val > self._threshold
            and state.n_samples >= self._min_samples
            and (state.n_samples - state.last_alarm_at) >= self._min_samples
        )
        if drift:
            state.last_alarm_at = state.n_samples

        return DriftResult(
            drift_detected=drift,
            arm=arm,
            cusum_value=round(cusum_val, 6),
            mean_reward=round(mu, 6),
            n_samples=state.n_samples,
        )

    def reset_arm(self, arm: int) -> None:
        self._arms[arm] = ArmDriftState()

    def get_state(self, arm: int) -> Optional[ArmDriftState]:
        return self._arms.get(arm)

    def get_all_states(self) -> Dict[int, ArmDriftState]:
        return dict(self._arms)
