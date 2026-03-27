import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.guards import AgentCallGuard

@pytest.mark.asyncio
async def test_bug4_budget_exhaustion():
    # Verify AgentCallGuard stops infinite loops/excessive calls
    mock_llm = AsyncMock()
    # LLM suggests different 'research' actions to avoid circuit breaker
    mock_llm.generate_async.side_effect = [
        "Thought: I need to search 1. Action: research(find 1)",
        "Thought: I need to search 2. Action: research(find 2)",
        "Thought: I need to search 3. Action: research(find 3)"
    ]
    
    mock_research = AsyncMock()
    mock_research.execute.return_value = {"status": "ok", "data": "found nothing"}
    
    agents = {
        "research": mock_research
    }
    
    coordinator = CoordinatorAgent(agent_registry=agents, llm_client=mock_llm)
    
    # We expect it to stop after 8 calls (default max_total)
    # But for this test, let's manually trigger exhaustion if possible or just check functionality
    # Actually, CoordinatorAgent.run_turn has for _ in range(5), so total calls can't exceed 5 in one turn 
    # unless it's the coordinator itself looping.
    # The max_total=8 is more than the loop range(5), so it won't hit it in one run_turn call
    # unless it's configured lower.
    
    # Let's mock AgentCallGuard to have max_total=2 for this test
    # We can't easily inject it into the local scope of run_turn, 
    # but we can monkeypatch the class.
    
    import agent_core.agents.coordinator
    original_guard = agents.coordinator.AgentCallGuard
    try:
        class MockGuard(AgentCallGuard):
            def __init__(self, *args, **kwargs):
                super().__init__(max_total=2)
        
        agents.coordinator.AgentCallGuard = MockGuard
        
        result = await coordinator.run_turn("test")
        assert "Agent budget exhausted" in result
        assert mock_research.execute.call_count == 2
    finally:
        agents.coordinator.AgentCallGuard = original_guard

@pytest.mark.asyncio
async def test_bug6_streaming_generator_fix():
    # Verify generate_streaming doesn't crash from 'await' on generator
    from agent_core.llm.client import LLMClient
    
    client = LLMClient()
    
    # Mock ollama.AsyncClient
    mock_async_client = MagicMock()
    
    # helper for async generator
    async def mock_chat_gen(*args, **kwargs):
        yield {"message": {"content": "Hello"}}
        yield {"message": {"content": " world"}}
        
    mock_async_client.chat.return_value = mock_chat_gen()
    
    # Patch the import in llm.client
    import agent_core.llm.client
    with MagicMock() as mock_ollama:
        mock_ollama.AsyncClient.return_value = mock_async_client
        # We need to ensure 'from ollama import AsyncClient' inside generate_streaming gets our mock
        # This is tricky because it's an inside-method import.
        # We can patch 'ollama.AsyncClient' directly if it's already imported or use sys.modules
        import sys
        sys.modules['ollama'] = mock_ollama
        
        tokens = []
        async for token in client.generate_streaming(messages=[{"role": "user", "content": "hi"}]):
            tokens.append(token)
            
        assert "".join(tokens) == "Hello world"
        del sys.modules['ollama']

@pytest.mark.asyncio
async def test_bug5_redundant_ensure_chain():
    # Verify _ensure_chain is only called once
    coordinator = CoordinatorAgent()
    coordinator.tree_store = MagicMock()
    coordinator.tree_store.get_chain_by_session_id_async = AsyncMock(return_value=MagicMock(id=123))
    
    # run_turn calls _ensure_chain once
    # We can track calls to get_chain_by_session_id_async
    await coordinator.run_turn("hello")
    # Intent greeting might bypass it if it returns early?
    # Greeting returns early before _ensure_chain?
    # Let's check coordinator.py:99
    # line 104: await self._ensure_chain() is AFTER classification but BEFORE shortcuts?
    # No, greeting is at 118.
    
    assert coordinator.tree_store.get_chain_by_session_id_async.call_count == 1
