"""
tests/test_advanced_architecture.py
===================================
Integration tests for the modular coordinator architecture.
- Pattern 4: LangGraph orchestration.
- Pattern 7: Redis A2A bus.
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from agents.orchestrator import OrchestratorAgent, BridgeAgent
from agents.a2a_bus import A2ABus
from core.agent_types import AgentRole, Intent

@pytest.mark.asyncio
async def test_a2a_bus_transmission():
    """Verifies that Redis A2A bus can send and receive messages."""
    bus = A2ABus()
    test_role = "test_agent"
    payload = {"hello": "world"}
    
    # Listen in a separate task
    received = []
    async def listen_task():
        async for msg in bus.listen(test_role):
            received.append(msg)
            break
            
    listener = asyncio.create_task(listen_task())
    await asyncio.sleep(0.5) # Wait for subscription
    
    await bus.send(test_role, payload)
    await asyncio.wait_for(listener, timeout=5.0)
    
    assert len(received) == 1
    assert received[0] == payload
    await bus.close()

@pytest.mark.asyncio
async def test_coordinator_graph_execution_mocked():
    """Verifies the coordinator graph flow with mocked LLM."""
    # Mock LLM and other deps
    mock_llm = MagicMock()
    mock_llm.generate_async = AsyncMock(return_value="Thought: I should use the research agent. Action: research(\"test query\")")
    
    coordinator = OrchestratorAgent(llm_client=mock_llm)
    mock_llm.generate_async.side_effect = [
        "Thought: I should use the research agent. Action: research(\"test query\")",
        "Final Response: Reasearch shows the project is on track."
    ]
    
    # Mock BridgeAgent to avoid real specialist execution
    mock_bridge = MagicMock(spec=BridgeAgent)
    mock_bridge.execute = AsyncMock(return_value={"message": "Research result"})
    coordinator.agents["research"] = mock_bridge
    
    # We also need to mock the classify_intent call in both places where it is imported
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("agents.orchestrator.classify_intent", lambda x: Intent.RAG_LOOKUP)
        mp.setattr("agents.graph.coordinator_graph.classify_intent", lambda x: Intent.RAG_LOOKUP)
        
        response = await coordinator.run_turn("Tell me about the project.")
        
        # Verify result
        assert "Reasearch shows" in str(response)
        # Note: Depending on the prompt and parse_react_action, it might continue or finish.
        # But here we verify it didn't crash and called the bridge.
        mock_bridge.execute.assert_called()

if __name__ == "__main__":
    pytest.main([__file__])
