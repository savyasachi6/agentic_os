import pytest
import math
from rl_router.domain.reward import RewardCalculator, RewardCoefficients
from rl_router.domain.models import ToolCallLog, HallucinationCategory

def test_reward_scaling_success():
    calc = RewardCalculator(RewardCoefficients(alpha_success=1.0, beta_step=0.1))
    # T=1, no invalid calls
    r1 = calc.compute_differentiated_utility(success=True, latency_ms=100.0, step_count=1)
    # T=5, no invalid calls
    r5 = calc.compute_differentiated_utility(success=True, latency_ms=100.0, step_count=5)
    
    # R(success) - 0.1*1 - latency vs R(success) - 0.1*5 - latency
    assert r1 > r5
    assert math.isclose(r1 - r5, 0.4, rel_tol=1e-2)

def test_invalid_call_penalty():
    calc = RewardCalculator(RewardCoefficients(gamma_invalid=0.5))
    r0 = calc.compute_differentiated_utility(success=True, latency_ms=100.0, invalid_call_count=0)
    r2 = calc.compute_differentiated_utility(success=True, latency_ms=100.0, invalid_call_count=2)
    
    assert r0 > r2
    assert math.isclose(r0 - r2, 1.0, rel_tol=1e-2)

def test_dual_discounting_heuristic():
    calc = RewardCalculator(RewardCoefficients(gamma_token=0.9, lambda_tool_cost=1.0))
    
    # 100 tokens
    tc1 = ToolCallLog(tool_name="t1", cost_tokens=100, execution_latency_ms=0, hallucination_type=HallucinationCategory.NONE)
    r100 = calc.compute_differentiated_utility(success=True, latency_ms=0, tool_calls=[tc1])
    
    # 200 tokens
    tc2 = ToolCallLog(tool_name="t2", cost_tokens=200, execution_latency_ms=0, hallucination_type=HallucinationCategory.NONE)
    r200 = calc.compute_differentiated_utility(success=True, latency_ms=0, tool_calls=[tc2])
    
    # p_tool for 100: 100 * 1.0 * (0.9 ** 1) = 90
    # p_tool for 200: 200 * 1.0 * (0.9 ** 2) = 162
    # Expectation: r200 should be lower than r100 because cost is higher
    assert r100 > r200

if __name__ == "__main__":
    pytest.main([__file__])
