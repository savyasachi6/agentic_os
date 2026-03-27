import pytest
from unittest.mock import patch, MagicMock
from agent_core.agents.core.coordinator import CoordinatorAgent
from agent_core.graph.state import AgentState
from agent_core.rag.retriever import SkillRetriever
from agent_core.rag.vector_store import VectorStore

@pytest.mark.asyncio
async def test_system_of_systems_health():
    """
    E2E Health Check: Core + Memory + Skills
    Verified that the orchestrator can reach its subsystems.
    """
    # 1. Mock the external heavy dependencies (DB, LLM, and Ollama)
    with patch("db.connection.get_db_connection") as mock_get_conn_db, \
         patch("db.queries.thoughts.get_db_connection", new=mock_get_conn_db), \
         patch("db.queries.skills.get_db_connection", new=mock_get_conn_db), \
         patch("db.queries.docs.get_db_connection", new=mock_get_conn_db), \
         patch("db.queries.tools.get_db_connection", new=mock_get_conn_db), \
         patch("db.queries.commands.get_db_connection", new=mock_get_conn_db), \
         patch("db.queries.events.get_db_connection", new=mock_get_conn_db), \
         patch("rag.rag_store.get_db_connection", new=mock_get_conn_db), \
         patch("agents.capability_agent.get_db_connection", new=mock_get_conn_db), \
         patch("db.connection.init_db_pool"), \
         patch("llm.client.LLMClient") as mock_llm_client, \
         patch("ollama.embeddings") as mock_embeddings, \
         patch("ollama.chat") as mock_chat, \
         patch("pgvector.psycopg2.register_vector"):
        
        # Setup mock returns
        mock_embeddings.return_value = {"embedding": [0.1] * 1536}
        mock_chat.return_value = {"message": {"content": "Sample response"}}
        
        # Setup mock DB context manager
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        
        mock_get_conn_db.return_value = mock_context
        
        # Mock returns for database queries
        # 1. create_chain / get_chain returns (id, session_id, description, created_at)
        from datetime import datetime
        mock_cur.fetchone.return_value = [1, "health-test", "Health check chain", datetime.now()]
        
        # 2. add_node returns (id, created_at, updated_at)
        # Note: if fetchone is called again, it will return the same thing unless we use side_effect
        mock_cur.fetchone.side_effect = [
            [1, "health-test", "Health check chain", datetime.now()], # For get_chain or create_chain
            [101, datetime.now(), datetime.now()], # For add_node RETURNING
        ]
        
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
        
        agent = CoordinatorAgent()
        # Manually override the llm and state to match our mocks/instances
        agent.llm = llm_instance
        agent.state = state
        agent.skill_retriever = retriever
        
        # 4. Run a single turn
        result = await agent.run_turn("System check")
        
        # 5. Verify Integration
        assert "integrated" in result.lower()
        print("[HealthCheck] Core-Memory-Skills integration verified.")
