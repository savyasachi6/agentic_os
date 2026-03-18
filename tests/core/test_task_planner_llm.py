import pytest
from unittest.mock import AsyncMock, patch
from productivity.task_planner import TaskPlanner
from productivity.models import TaskPlan, PlanStep, PlanStepStatus

@pytest.mark.asyncio
async def test_create_plan_llm_integration():
    """
    Test that create_plan calls the LLM and parses the structured output into a TaskPlan.
    """
    mock_tool_registry = {}
    planner = TaskPlanner(mock_tool_registry)
    
    # Define a dummy LLM response
    expected_plan = TaskPlan(
        id="test-plan-123",
        goal="Decompose a goal",
        steps=[
            PlanStep(action="Search", tool_name="web_search", args={"query": "test"}),
            PlanStep(action="Done", status=PlanStepStatus.DONE)
        ]
    )
    
    # Mock the generate_structured_output function
    with patch("productivity.task_planner.generate_structured_output", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = expected_plan
        
        plan = await planner.create_plan("My complex goal")
        
        assert plan.goal == "My complex goal"
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "web_search"
        mock_gen.assert_called_once()
        # Verify the prompt contains the goal
        args, kwargs = mock_gen.call_args
        assert "My complex goal" in kwargs["prompt"]

@pytest.mark.asyncio
async def test_create_plan_failure_fallback():
    """
    Test that create_plan handles LLM failures gracefully (e.g. returns a plan with an error step).
    """
    mock_tool_registry = {}
    planner = TaskPlanner(mock_tool_registry)
    
    with patch("productivity.task_planner.generate_structured_output", new_callable=AsyncMock) as mock_gen:
        # Simulate a parse error or model failure
        mock_gen.side_effect = Exception("LLM Down")
        
        plan = await planner.create_plan("Failing goal")
        
        assert plan.goal == "Failing goal"
        assert len(plan.steps) == 1
        assert "failed" in plan.steps[0].action.lower()
        assert plan.steps[0].status == PlanStepStatus.FAILED
