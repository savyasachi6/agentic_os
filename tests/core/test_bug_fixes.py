import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agents.intent.classifier import classify_intent, is_llm_generatable
from core.agent_types import Intent
from agents.orchestrator import OrchestratorAgent

@pytest.mark.asyncio
async def test_bug1_news_intent():
    # BUG 1: "what is the news for today" should be WEB_SEARCH
    message = "what is the news for today"
    intent = classify_intent(message)
    assert intent == Intent.WEB_SEARCH

@pytest.mark.asyncio
async def test_bug2_3_llm_generatable():
    # BUG 2 & 3: "agent architecture patterns" should be llm_generatable
    # and COMPLEX_TASK or WEB_SEARCH (if it contains 'news', but here architectural)
    message = "agent architecture patterns"
    assert is_llm_generatable(message) is True
    
    # "generate an outline" should be llm_generatable
    assert is_llm_generatable("generate an outline for a project") is True

@pytest.mark.asyncio
async def test_bug4_circuit_breaker():
    # BUG 4: Specialist failure should be handled by ReAct loop
    
    # Mock agents
    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = Exception("Planned command failed")
    
    mock_llm = AsyncMock()
    mock_llm.generate_async.side_effect = [
        "Thought: I will run a command. Action: code(echo hello)",
        "Action: respond(Final answer after failure)"
    ]
    
    agents = {
        "executor": mock_executor,
        "code": mock_executor
    }
    
    coordinator = OrchestratorAgent(agent_registry=agents, llm_client=mock_llm)
    
    # This should call code (fail) -> LLM -> respond
    message = "run a command"
    result = await coordinator.run_turn(message)
    
    assert mock_executor.execute.call_count == 1
    assert "Final answer" in result

@pytest.mark.asyncio
async def test_intent_classification_heuristics():
    # Test some of the new classifications
    assert classify_intent("search the web for apple stock") == Intent.WEB_SEARCH
    assert classify_intent("write a python script to sort a list") == Intent.CODE_GEN
    assert classify_intent("summarize the document about agents") == Intent.LLM_DIRECT
    assert classify_intent("what can you do?") == Intent.CAPABILITY_QUERY
