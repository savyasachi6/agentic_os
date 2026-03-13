"""
LinUCB contextual bandit with multi-objective safety-aware UCB,
exponential decay for non-stationarity, and CUSUM drift integration.

Pure domain logic — no FastAPI, no DB, no config singletons.
All hyperparameters are injected at construction time.
"""

import io
import threading
from typing import List, Tuple, Dict, Any

import numpy as np

from agentic_rl_router.domain.drift import CUSUMDriftDetector, DriftResult


class LinUCBBandit:
    """Thread-safe LinUCB contextual bandit with safety-aware exploration."""

    def __init__(
        self,
        n_arms: int = 8,
        d: int = 1561,
        alpha: float = 1.5,
        tau: float = 0.995,
        viol_lambda: float = 0.3,
        drift_threshold: float = 5.0,
        drift_sensitivity: float = 0.05,
        drift_min_samples: int = 30,
    ) -> None:
        self.n_arms = n_arms
        self.d = d
        self.alpha = alpha
        self.tau = tau
        self.viol_lambda = viol_lambda

        self._A_inv: List[np.ndarray] = [np.eye(self.d) for _ in range(self.n_arms)]
        self._b: List[np.ndarray] = [np.zeros(self.d) for _ in range(self.n_arms)]

        self._violation_counts: np.ndarray = np.zeros(self.n_arms)
        self._pull_counts: np.ndarray = np.zeros(self.n_arms)
        self._sum_rewards: np.ndarray = np.zeros(self.n_arms)

        self._drift = CUSUMDriftDetector(
            n_arms=n_arms,
            threshold=drift_threshold,
            drift_sensitivity=drift_sensitivity,
            min_samples=drift_min_samples,
        )
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Arm selection
    # ------------------------------------------------------------------

    def select_arm(self, context: np.ndarray) -> Tuple[int, List[float], bool]:
        """Select arm with highest safety-aware UCB score.

        Returns (best_arm, ucb_scores, is_exploration).
        """
        x = context.astype(np.float64).flatten()

        ucb_scores: List[float] = []

        with self._lock:
            for a in range(self.n_arms):
                A_inv = self._A_inv[a]
                theta = A_inv @ self._b[a]

                mean = float(theta @ x)
                exploration = self.alpha * float(np.sqrt(x @ A_inv @ x))

                viol_rate = self._violation_rate(a)
                adjusted_mean = mean - self.viol_lambda * viol_rate

                ucb_scores.append(adjusted_mean + exploration)

        best_arm = int(np.argmax(ucb_scores))

        with self._lock:
            A_inv = self._A_inv[best_arm]
            theta = A_inv @ self._b[best_arm]
            best_mean = abs(float(theta @ x))
            best_expl = self.alpha * float(np.sqrt(x @ A_inv @ x))
        is_exploration = best_expl > best_mean

        return best_arm, ucb_scores, is_exploration

    # ------------------------------------------------------------------
    # Policy update
    # ------------------------------------------------------------------

    def update(
        self,
        arm: int,
        context: np.ndarray,
        reward: float,
        hallucination_flag: bool = False,
    ) -> DriftResult:
        """Online update with Sherman-Morrison and exponential decay."""
        x = context.astype(np.float64).reshape(-1, 1)

        with self._lock:
            # 1. Sherman-Morrison update for A_inv
            # New A_inv = (τA + xx^T)^-1
            # First, account for decay τ: A_new = τA => A_inv_new = (1/τ) * A_inv
            self._A_inv[arm] /= self.tau
            
            # Then apply rank-1 update: (A + xx^T)^-1 = A^-1 - (A^-1 x x^T A^-1) / (1 + x^T A^-1 x)
            A_inv = self._A_inv[arm]
            inv_x = A_inv @ x
            denominator = 1.0 + (x.T @ inv_x).item()
            self._A_inv[arm] = A_inv - (inv_x @ inv_x.T) / denominator

            self._b[arm] = self.tau * self._b[arm] + reward * x.flatten()

            self._pull_counts[arm] += 1
            self._sum_rewards[arm] += reward
            if hallucination_flag:
                self._violation_counts[arm] += 1

        drift_result = self._drift.update(arm, reward)
        if drift_result.drift_detected:
            self.soft_reset(arm)

        return drift_result

    # ------------------------------------------------------------------
    # Resets
    # ------------------------------------------------------------------

    def soft_reset(self, arm: int, retain_fraction: float = 0.3) -> None:
        with self._lock:
            # Scale up A_inv to increase uncertainty
            self._A_inv[arm] /= retain_fraction
            # Scale down b by retain_fraction^2 to ensure theta (A_inv @ b) shrinks by retain_fraction
            self._b[arm] *= (retain_fraction * retain_fraction)
            self._violation_counts[arm] *= retain_fraction
            self._pull_counts[arm] *= retain_fraction
            self._sum_rewards[arm] *= retain_fraction
        self._drift.reset_arm(arm)

    def hard_reset(self) -> None:
        with self._lock:
            self._A_inv = [np.eye(self.d) for _ in range(self.n_arms)]
            self._b = [np.zeros(self.d) for _ in range(self.n_arms)]
            self._violation_counts = np.zeros(self.n_arms)
            self._pull_counts = np.zeros(self.n_arms)
            self._sum_rewards = np.zeros(self.n_arms)
        for a in range(self.n_arms):
            self._drift.reset_arm(a)

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def _violation_rate(self, arm: int) -> float:
        if self._pull_counts[arm] == 0:
            return 0.0
        return float(self._violation_counts[arm] / self._pull_counts[arm])

    def get_arm_stats(self, arm: int) -> dict:
        with self._lock:
            A_inv = self._A_inv[arm]
            theta = A_inv @ self._b[arm]
            theta_norm = float(np.linalg.norm(theta))
            pulls = int(self._pull_counts[arm])
            viol_rate = self._violation_rate(arm)
            mean_reward = float(self._sum_rewards[arm] / pulls) if pulls > 0 else 0.0

        drift_state = self._drift.get_state(arm)
        return {
            "arm": arm,
            "pulls": pulls,
            "theta_norm": round(theta_norm, 6),
            "violation_rate": round(viol_rate, 6),
            "mean_reward": round(mean_reward, 6),
            "cusum_pos": round(drift_state.cusum_pos, 6) if drift_state else 0.0,
            "cusum_neg": round(drift_state.cusum_neg, 6) if drift_state else 0.0,
        }

    def get_all_arm_stats(self) -> list[dict]:
        return [self.get_arm_stats(a) for a in range(self.n_arms)]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_bytes(self) -> bytes:
        """Serializes current bandit weights and state to a compressed bytes buffer."""
        with self._lock:
            data = {
                "A_inv": np.stack(self._A_inv),
                "b": np.stack(self._b),
                "violation_counts": self._violation_counts,
                "pull_counts": self._pull_counts,
                "sum_rewards": self._sum_rewards,
                "d": self.d,
            }
            buffer = io.BytesIO()
            np.savez_compressed(buffer, **data)
            return buffer.getvalue()

    def load_from_bytes(self, data_bytes: bytes) -> None:
        """Deserializes bandit weights and state from a compressed bytes buffer."""
        buffer = io.BytesIO(data_bytes)
        with np.load(buffer) as data:
            with self._lock:
                self._A_inv = [arm_data for arm_data in data["A_inv"]]
                self._b = [arm_data for arm_data in data["b"]]
                self._violation_counts = data["violation_counts"]
                self._pull_counts = data["pull_counts"]
                if "sum_rewards" in data:
                    self._sum_rewards = data["sum_rewards"]
                if "d" in data:
                    self.d = int(data["d"])
                for a in range(self.n_arms):
                    self._drift.reset_arm(a)
