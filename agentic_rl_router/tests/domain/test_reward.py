"""Tests for the multi-objective reward calculator (domain layer)."""

from agentic_rl_router.domain.reward import RewardCalculator, RewardCoefficients


def _calc(**overrides) -> RewardCalculator:
    defaults = dict(
        lambda_h=0.8, lambda_l=0.1, gamma=0.15,
        l0_ms=250.0, kappa=2.0, hallucination_hard_cap=-0.3,
    )
    defaults.update(overrides)
    return RewardCalculator(RewardCoefficients(**defaults))


class TestRewardVector:
    def test_perfect_success_no_hallucination(self) -> None:
        r = _calc().compute(success=True, latency_ms=200, hallucination_flag=False, hallucination_score=0.0)
        assert r.quality == 1.0
        assert r.hallucination_penalty == 0.0
        assert r.overthinking_penalty == 0.0
        assert r.scalar > 0.0

    def test_hallucination_flag_dominates(self) -> None:
        r = _calc().compute(success=True, latency_ms=50, hallucination_flag=True, hallucination_score=0.0)
        assert r.hallucination_penalty < 0
        assert r.scalar <= -0.3

    def test_hallucination_score_gradient(self) -> None:
        low = _calc().compute(success=True, latency_ms=100, hallucination_flag=False, hallucination_score=0.1)
        high = _calc().compute(success=True, latency_ms=100, hallucination_flag=False, hallucination_score=0.8)
        assert high.hallucination_penalty < low.hallucination_penalty

    def test_latency_log_smoothing(self) -> None:
        fast = _calc().compute(success=True, latency_ms=100, hallucination_flag=False)
        slow = _calc().compute(success=True, latency_ms=5000, hallucination_flag=False)
        assert fast.latency_cost > slow.latency_cost
        assert slow.scalar < fast.scalar

    def test_overthinking_penalty(self) -> None:
        r = _calc().compute(success=True, latency_ms=200, hallucination_flag=False, depth_used=3, min_sufficient_depth=1)
        expected = -0.15 * 2
        assert abs(r.overthinking_penalty - expected) < 1e-6

    def test_no_overthinking_when_depth_matches(self) -> None:
        r = _calc().compute(success=True, latency_ms=200, hallucination_flag=False, depth_used=1, min_sufficient_depth=1)
        assert r.overthinking_penalty == 0.0

    def test_auditor_score_overrides_success(self) -> None:
        r = _calc().compute(success=False, latency_ms=200, hallucination_flag=False, auditor_score=0.9)
        assert r.quality == 0.9

    def test_zero_latency(self) -> None:
        r = _calc().compute(success=True, latency_ms=0, hallucination_flag=False)
        assert r.latency_cost == 0.0

    def test_hallucination_hard_cap_worse_than_threshold(self) -> None:
        r = _calc(hallucination_hard_cap=-0.5).compute(
            success=True, latency_ms=50, hallucination_flag=True, hallucination_score=0.1)
        assert r.scalar <= -0.5


class TestDifferentiatedUtility:
    from agentic_rl_router.domain.models import HallucinationCategory, ToolCallLog
    
    def test_perfect_reliable_pass(self) -> None:
        tc = self.ToolCallLog(tool_name="search", cost_tokens=100)
        calc = _calc()
        u = calc.compute_differentiated_utility(success=True, latency_ms=100, tool_calls=[tc])
        assert calc.is_reliable_pass(success=True, tool_calls=[tc]) is True
        # 1.0 (task) - latency - (100 * 1e-4) - 0.0
        assert u > 0.8
    
    def test_format_hallucination_penalty(self) -> None:
        tc = self.ToolCallLog(tool_name="search", cost_tokens=100, hallucination_type=self.HallucinationCategory.FORMAT)
        calc = _calc()
        u = calc.compute_differentiated_utility(success=True, latency_ms=100, tool_calls=[tc])
        assert calc.is_reliable_pass(success=True, tool_calls=[tc]) is False
        # Penalty is 0.5, so utility drops vs perfect
        assert u > 0.0 and u < 0.6
        
    def test_content_hallucination_dominates(self) -> None:
        tc = self.ToolCallLog(tool_name="db", cost_tokens=10, hallucination_type=self.HallucinationCategory.CONTENT)
        calc = _calc()
        u = calc.compute_differentiated_utility(success=True, latency_ms=100, tool_calls=[tc])
        # Penalty is 4.0, so: 1.0 - lat - 0.001 - 4.0 ≈ -3.0
        assert u < -2.5
        
    def test_failure_is_not_reliable_pass(self) -> None:
        tc = self.ToolCallLog(tool_name="search")
        assert _calc().is_reliable_pass(success=False, tool_calls=[tc]) is False


class TestDifferentiatedUtility:
    """Tests for RelyToolBench Benefit-Cost Utility (final_utility_score)."""

    def test_perfect_success_with_no_tools(self) -> None:
        u = _calc().compute_differentiated_utility(success=True, latency_ms=0)
        assert u == 1.0  # R_task = 1, no latency, no tools

    def test_latency_penalty_applied(self) -> None:
        u = _calc().compute_differentiated_utility(success=True, latency_ms=250)
        # R_task=1.0 - lambda_l * ln(1 + 250/250) = 1.0 - 0.1 * ln(2) ~ 0.930685
        assert 0.93 < u < 0.94

    def test_failure_is_negative(self) -> None:
        u = _calc().compute_differentiated_utility(success=False, latency_ms=0)
        assert u == -1.0

    def test_tool_cost_penalty(self) -> None:
        from agentic_rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="search", cost_tokens=1000)]
        # Default lambda_tool_cost is 1e-4 -> penalty is 0.1
        u = _calc().compute_differentiated_utility(success=True, latency_ms=0, tool_calls=tools)
        assert u == 0.9

    def test_differentiated_hallucination_penalties(self) -> None:
        from agentic_rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [
            ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.FORMAT),   # p = 0.5
            ToolCallLog(tool_name="t2", hallucination_type=HallucinationCategory.TIMING),   # p = 1.0
            ToolCallLog(tool_name="t3", hallucination_type=HallucinationCategory.TYPE),     # p = 2.0
            ToolCallLog(tool_name="t4", hallucination_type=HallucinationCategory.CONTENT),  # p = 4.0
        ]
        u = _calc().compute_differentiated_utility(success=True, latency_ms=0, tool_calls=tools)
        # R_task=1.0, penalties = 0.5 + 1.0 + 2.0 + 4.0 = 7.5 -> Utility = -6.5
        assert u == -6.5


class TestReliablePass:
    """Tests for the RePR metric indicator (reliable_pass_flag)."""

    def test_reliable_pass_success_no_tools(self) -> None:
        assert _calc().is_reliable_pass(success=True) is True

    def test_reliable_pass_success_clean_tools(self) -> None:
        from agentic_rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE)]
        assert _calc().is_reliable_pass(success=True, tool_calls=tools) is True

    def test_fails_on_any_hallucination(self) -> None:
        from agentic_rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [
            ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE),
            ToolCallLog(tool_name="t2", hallucination_type=HallucinationCategory.FORMAT),
        ]
        assert _calc().is_reliable_pass(success=True, tool_calls=tools) is False

    def test_fails_if_task_fails(self) -> None:
        from agentic_rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE)]
        assert _calc().is_reliable_pass(success=False, tool_calls=tools) is False
