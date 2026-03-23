"""
Multi-Fidelity Reward Shaping for the RL Router.
Balances three conflicting signals: Auditor Accuracy, Latency, and Agent Success.
"""

from typing import Optional

class CompositeReward:
    """Computes a multi-fidelity reward for the RL Contextual Bandit."""

    @staticmethod
    def compute(
        auditor_score: float,
        latency_ms: float,
        looped_back_to_fixer: bool
    ) -> float:
        """
        Computes the composite reward.
        
        1. The Auditor Signal (Accuracy):
           If 0.9 -> +1.0, If 0.2 -> -2.0.
           Linear interpolation: reward = (auditor_score * 30/7) - 20/7
        2. The Latency Penalty (Efficiency):
           Penalty = (time_taken_ms / 10) 
           Note: Usually latency in RL is ms, but if time_taken is meant to be seconds, 
           we scale appropriately. Assuming time_taken here is in milliseconds,
           we might divide by 1000 to get seconds, then divide by 10. Let's assume 
           the prompt meant `latency_seconds / 10`. So `(latency_ms / 1000) / 10 = latency_ms / 10000`.
           Wait, if latency is 100ms, 100/10 = 10, penalty -10? That's huge. 
           Let's use latency_ms / 10000.0 or just parameterize it.
        3. The Agent Success Signal:
           Negative reward if loop back.
        """
        # 1. Auditor Signal (Linear function mapping 0.9->1.0 and 0.2->-2.0)
        # m = (1.0 - (-2.0)) / (0.9 - 0.2) = 3.0 / 0.7 = 30/7 ≈ 4.2857
        # b = 1.0 - (30/7)*0.9 = -20/7 ≈ -2.8571
        auditor_reward = (auditor_score * (30.0 / 7.0)) - (20.0 / 7.0)

        # 2. Latency Penalty
        # "time_taken / 10" - we assume time_taken here is in milliseconds 
        # but logically if it takes 2000ms (2s), 2s/10 = 0.2 penalty. 
        # So we do (latency_ms / 1000.0) / 10.0
        time_taken_sec = latency_ms / 1000.0
        latency_penalty = time_taken_sec / 10.0

        # 3. Agent Success Signal
        factor_backtrack = -5.0 if looped_back_to_fixer else 0.0

        total_reward = auditor_reward - latency_penalty + factor_backtrack
        return total_reward
