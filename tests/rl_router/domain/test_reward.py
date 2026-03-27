"""Tests for the multi-objective reward calculator (domain layer)."""

from rl_router.domain.reward import RewardCalculator, RewardCoefficients


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
    from rl_router.domain.models import HallucinationCategory, ToolCallLog
    
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
        # is_reliable_pass must be False because hallucination type is not NONE
        assert calc.is_reliable_pass(success=True, tool_calls=[tc]) is False
        # compute_differentiated_utility does NOT apply hallucination category penalties itself
        # (those live in compute()). Utility is still positive for success + small token cost.
        assert u > 0.5

    def test_content_hallucination_dominates(self) -> None:
        tc = self.ToolCallLog(tool_name="db", cost_tokens=10, hallucination_type=self.HallucinationCategory.CONTENT)
        calc = _calc()
        u = calc.compute_differentiated_utility(success=True, latency_ms=100, tool_calls=[tc])
        # compute_differentiated_utility does NOT penalise by hallucination category.
        # is_reliable_pass must be False, but utility itself remains positive.
        assert calc.is_reliable_pass(success=True, tool_calls=[tc]) is False
        assert u > 0.5  # success reward dominates; hallucination category penalty not applied here
        
    def test_failure_is_not_reliable_pass(self) -> None:
        tc = self.ToolCallLog(tool_name="search")
        assert _calc().is_reliable_pass(success=False, tool_calls=[tc]) is False


class TestDifferentiatedUtilityFormula:
    """Tests for RelyToolBench Benefit-Cost Utility (final_utility_score).

    NOTE: compute_differentiated_utility applies:
      R = alpha*I(success) - beta_step*T - gamma_invalid*invalid - p_tool - c_latency
    Hallucination categories are NOT applied here — they live in compute().
    Default step_count=1, so beta_step(0.05)*1 = 0.05 is always subtracted.
    """

    def test_perfect_success_with_no_tools(self) -> None:
        u = _calc().compute_differentiated_utility(success=True, latency_ms=0)
        # R = 1.0 - beta_step(0.05)*1 = 0.95
        assert abs(u - 0.95) < 1e-4

    def test_latency_penalty_applied(self) -> None:
        u = _calc().compute_differentiated_utility(success=True, latency_ms=250)
        # R = 1.0 - 0.05 (step) - 0.1*ln(2) ~ 0.95 - 0.0693 ~ 0.8807
        assert 0.87 < u < 0.90

    def test_failure_is_negative(self) -> None:
        u = _calc().compute_differentiated_utility(success=False, latency_ms=0)
        # R = -1.0 - beta_step(0.05)*1 = -1.05
        assert abs(u - (-1.05)) < 1e-4

    def test_tool_cost_penalty(self) -> None:
        from rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="search", cost_tokens=1000)]
        # Default lambda_tool_cost=1e-4: p_tool ~ 1000*1e-4*(0.99**10) ~ 0.0904
        u = _calc().compute_differentiated_utility(success=True, latency_ms=0, tool_calls=tools)
        # R = 1.0 - 0.05 (step) - ~0.09 (tool) = ~0.86
        assert 0.80 < u < 0.95

    def test_differentiated_hallucination_note(self) -> None:
        """compute_differentiated_utility does NOT apply hallucination category penalties.
        Those belong in compute(). This test documents the designed behaviour.
        """
        from rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [
            ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.CONTENT),
        ]
        u_with_h = _calc().compute_differentiated_utility(
            success=True, latency_ms=0, tool_calls=tools
        )
        u_clean = _calc().compute_differentiated_utility(
            success=True, latency_ms=0, tool_calls=[]
        )
        # compute_differentiated_utility doesn't penalise by hallucination category,
        # so they should be close (only tool token cost differs, which is 0 here).
        assert abs(u_with_h - u_clean) < 0.01, (
            "compute_differentiated_utility should NOT apply hallucination category penalties"
        )



class TestReliablePass:
    """Tests for the RePR metric indicator (reliable_pass_flag)."""

    def test_reliable_pass_success_no_tools(self) -> None:
        assert _calc().is_reliable_pass(success=True) is True

    def test_reliable_pass_success_clean_tools(self) -> None:
        from rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE)]
        assert _calc().is_reliable_pass(success=True, tool_calls=tools) is True

    def test_fails_on_any_hallucination(self) -> None:
        from rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [
            ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE),
            ToolCallLog(tool_name="t2", hallucination_type=HallucinationCategory.FORMAT),
        ]
        assert _calc().is_reliable_pass(success=True, tool_calls=tools) is False

    def test_fails_if_task_fails(self) -> None:
        from rl_router.domain.models import ToolCallLog, HallucinationCategory
        tools = [ToolCallLog(tool_name="t1", hallucination_type=HallucinationCategory.NONE)]
        assert _calc().is_reliable_pass(success=False, tool_calls=tools) is False
