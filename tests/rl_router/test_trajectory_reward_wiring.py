"""
tests/rl_router/test_trajectory_reward_wiring.py
=================================================
Verifies that FeedbackService.process_feedback() uses compute_differentiated_utility
(trajectory-level reward) whenever step_count > 1 or invalid_call_count > 0,
regardless of whether tool_calls is provided.

Also verifies backward compatibility: step_count=1, invalid_call_count=0, tool_calls=[]
still uses the legacy scalar (final_utility_score should be None).
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from rl_router.application.services.feedback_service import FeedbackService
from rl_router.domain.reward import RewardCalculator, RewardCoefficients
from rl_router.schemas.api_models import FeedbackRequest, FeedbackResponse


def _make_service() -> FeedbackService:
    """Build a FeedbackService with lightweight mocks for infra dependencies."""
    bandit = MagicMock()
    bandit.d = 10
    bandit.update.return_value = MagicMock(drift_detected=False)

    reward_calc = RewardCalculator(RewardCoefficients())

    episode_repo = MagicMock()
    episode_repo.log_episode.return_value = "test-episode-id"

    tool_exec_repo = MagicMock()

    return FeedbackService(
        bandit=bandit,
        reward_calc=reward_calc,
        episode_repo=episode_repo,
        tool_exec_repo=tool_exec_repo,
    )


def _base_request(**kwargs) -> FeedbackRequest:
    defaults = dict(
        query_hash="abc123",
        arm_index=2,
        depth_used=1,
        latency_ms=200,
        success=True,
        step_count=1,
        invalid_call_count=0,
        tool_calls=[],
    )
    defaults.update(kwargs)
    return FeedbackRequest(**defaults)


# ---------------------------------------------------------------------------
# Test 1: Trajectory reward activated by step_count > 1 (no tool_calls)
# ---------------------------------------------------------------------------

def test_trajectory_reward_used_when_step_count_above_one():
    """step_count=3 should trigger compute_differentiated_utility and return a non-None final_utility_score."""
    svc = _make_service()

    with patch("rl_router.infrastructure.context_cache.context_registry") as mock_reg:
        mock_reg.pop.return_value = np.zeros(10)
        req = _base_request(step_count=3, success=True)
        resp: FeedbackResponse = svc.process_feedback(req)

    assert resp.final_utility_score is not None, (
        "final_utility_score must be set when step_count > 1"
    )
    # With alpha=1.0, beta=0.05, step=3: R = 1.0 - 0.05*3 - latency_penalty ≈ 0.83xx
    assert resp.final_utility_score < 1.0  # step penalty applied
    assert resp.final_utility_score > 0.0  # but still positive for a success


# ---------------------------------------------------------------------------
# Test 2: Trajectory reward activated by invalid_call_count > 0
# ---------------------------------------------------------------------------

def test_trajectory_reward_used_when_invalid_calls_present():
    """invalid_call_count=2 should trigger compute_differentiated_utility."""
    svc = _make_service()

    with patch("rl_router.infrastructure.context_cache.context_registry") as mock_reg:
        mock_reg.pop.return_value = np.zeros(10)
        req = _base_request(invalid_call_count=2, success=True)
        resp: FeedbackResponse = svc.process_feedback(req)

    assert resp.final_utility_score is not None
    # With gamma_invalid=0.2, 2 invalid calls = -0.4 penalty applied
    no_invalid_req = _base_request(invalid_call_count=0, step_count=2, success=True)
    with patch("rl_router.infrastructure.context_cache.context_registry") as mock_reg2:
        mock_reg2.pop.return_value = np.zeros(10)
        resp_clean = svc.process_feedback(no_invalid_req)

    assert resp_clean.final_utility_score > resp.final_utility_score, (
        "Zero invalid calls should yield higher utility than 2 invalid calls"
    )


# ---------------------------------------------------------------------------
# Test 3: Backward compatibility — step_count=1, no invalids, no tool_calls
# ---------------------------------------------------------------------------

def test_legacy_path_preserved_for_simple_lookups():
    """Single-step lookups with no tool_calls should use legacy scalar (final_utility_score=None)."""
    svc = _make_service()

    with patch("rl_router.infrastructure.context_cache.context_registry") as mock_reg:
        mock_reg.pop.return_value = np.zeros(10)
        req = _base_request(step_count=1, invalid_call_count=0, tool_calls=[])
        resp: FeedbackResponse = svc.process_feedback(req)

    assert resp.final_utility_score is None, (
        "Legacy path should not compute differentiated utility for pure step_count=1 queries"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
