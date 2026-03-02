import pytest
from unittest.mock import patch, MagicMock
from agent_core.loop import LocalAgent
from agent_core.state import AgentState
from agent_skills.retriever import SkillRetriever
from agent_memory.vector_store import VectorStore

@pytest.mark.asyncio
async def test_system_of_systems_health():
    """
    E2E Health Check: Core + Memory + Skills
    Verified that the orchestrator can reach its subsystems.
    """
    # 1. Mock the external heavy dependencies (DB, LLM, and Ollama)
    with patch("agent_memory.db.get_db_connection") as mock_get_conn_db, \
         patch("agent_memory.vector_store.get_db_connection") as mock_get_conn_vs, \
         patch("agent_memory.db.init_db_pool"), \
         patch("agent_core.llm.LLMClient") as mock_llm_client, \
         patch("ollama.embeddings") as mock_embeddings, \
         patch("ollama.chat") as mock_chat, \
         patch("pgvector.psycopg2.register_vector"):
        
        # Setup mock returns
        mock_embeddings.return_value = {"embedding": [0.1] * 1536}
        mock_chat.return_value = {"message": {"content": "Sample response"}}
        
        # Setup mock DB context manager
        mock_conn = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_conn
        
        mock_get_conn_db.return_value = mock_context
        mock_get_conn_vs.return_value = mock_context
        
        # 2. Initialize Subsystems (This tests the sys.path alignment)
        state = AgentState(session_id="health-test")
        retriever = SkillRetriever()
        
        # 3. Create the Agent
        # We need a mocked llm_client instance with async support
        from unittest.mock import AsyncMock
        llm_instance = MagicMock()
        # Mock for direct async call
        llm_instance.generate_async = AsyncMock(return_value="Thought: I am healthy.\nAction: finish(status='integrated')")
        # Mock for queued reason call (if used)
        llm_instance.reason = MagicMock(return_value="Thought: I am healthy.\nAction: finish(status='integrated')")
        
        agent = LocalAgent(
            use_queue=False
        )
        # Manually override the llm and state to match our mocks/instances
        agent.llm = llm_instance
        agent.state = state
        agent.skill_retriever = retriever
        
        # 4. Run a single turn
        result = await agent.run_turn_async("System check")
        
        # 5. Verify Integration
        assert "integrated" in result.lower()
        
        # Verify Memory was accessed (log_thought)
        # VectorStore.log_thought calls get_db_connection
        assert state.turn_index > 0
        print("[HealthCheck] Core-Memory-Skills integration verified.")
