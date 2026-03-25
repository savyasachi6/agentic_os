import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.coordinator import CoordinatorAgent
from agent_core.types import Intent
from intent.classifier import classify_intent

@pytest.mark.asyncio
async def test_capability_intent_classification():
    """Verify that 'skills' queries are classified as CAPABILITY_QUERY."""
    assert classify_intent("what are some of the skills") == Intent.CAPABILITY_QUERY
    assert classify_intent("tell me about your skills") == Intent.CAPABILITY_QUERY
    assert classify_intent("what skills do you have") == Intent.CAPABILITY_QUERY

@pytest.mark.asyncio
async def test_greeting_intent_classification():
    """Verify that greetings are classified as GREETING."""
    assert classify_intent("hi") == Intent.GREETING
    assert classify_intent("hello there") == Intent.GREETING
    assert classify_intent("hey") == Intent.GREETING

@pytest.mark.asyncio
async def test_coordinator_direct_capability_call():
    """Verify that CoordinatorAgent.run_turn calls _handle_capability for capability queries."""
    # The new coordinator uses an agent registry. 
    # For a capability query, it calls agents["capability"].execute(message)
    
    mock_capability_agent = AsyncMock()
    mock_capability_agent.execute.return_value = {"answer": "Direct Capability Response"}
    
    mock_llm = AsyncMock()
    mock_llm.generate_async.side_effect = [
        "Action: capability(What can you do?)",
        "Action: respond(Final Answer)"
    ]

    agents = {
        "capability": mock_capability_agent
    }
    
    with patch('agents.coordinator.TreeStore') as mock_ts:
        ts = mock_ts.return_value
        ts.get_chain_by_session_id_async = AsyncMock(return_value=MagicMock(id=1))
        
        agent = CoordinatorAgent(agent_registry=agents, llm_client=mock_llm)
        
        # We call run_turn
        await agent.run_turn("What can you do?")
    
    assert mock_capability_agent.execute.call_count == 1
    mock_capability_agent.execute.assert_called_once()
