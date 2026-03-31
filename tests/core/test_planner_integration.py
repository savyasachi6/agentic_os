import pytest
from unittest.mock import AsyncMock, MagicMock
from agents.orchestrator import OrchestratorAgent
from core.agent_types import Intent, NodeStatus
from langchain_core.messages import AIMessage

@pytest.mark.asyncio
async def test_planner_integration_flow():
    """Verify that a complex task triggers the planner bridge."""
    # 1. Setup Coordinator
    coordinator = OrchestratorAgent()
    
    # 2. Mock the planner BridgeAgent
    mock_planner = AsyncMock()
    mock_planner.execute.return_value = {"message": "Plan: 1. Research 2. Implement"}
    coordinator.agents["planner"] = mock_planner
    
    # 3. Mock LLM to return a REACt action for the planner
    # The first call to generate_async (in route_node) should return the Action
    # The second call (if any, though here it might respond directly after observation) 
    # should return the final response.
    coordinator.llm.generate_async = AsyncMock(side_effect=[
        'Thought: This needs decomposition.\nAction: planner({"goal": "Decompose task X"})',
        'Final Answer: Here is the plan: 1. Research 2. Implement'
    ])
    
    # 4. Run turn with a message that will be classified as COMPLEX_TASK
    # (Length > 2 words and no other keywords)
    message = "I need a detailed plan for building a new microservice."
    response = await coordinator.run_turn(message)
    
    # 5. Assertions
    # Ensure bridge.execute was called with the right goal
    mock_planner.execute.assert_called_once()
    call_args = mock_planner.execute.call_args[0][0]
    assert "Decompose task X" in call_args["goal"]
    
    # Ensure the final response contains the expected content
    assert "1. Research" in response
    assert "2. Implement" in response
