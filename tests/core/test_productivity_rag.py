"""
Tests for the Memory/RAG integration via Productivity modules.

Validates the 'Semantic Memory' and 'Resilient RAG Pipeline' skills in [skill.md](../../skill.md).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from productivity.todo_manager import TodoManager
from productivity.notes import NoteManager
try:
    from db.cache import FractalCache, SemanticCache
except ImportError:
    import pytest
from db.models import Chain, Node, AgentRole, NodeType, NodeStatus
from rag.rag_store import RagStore

@pytest.mark.asyncio
async def test_todo_semantic_search_stub():
    """Verify TodoManager search structure is aligned with vector store intent."""
    manager = TodoManager(vector_store=MagicMock())
    manager.add_todo("Buy milk")
    results = manager.search_todos("milk")
    assert len(results) == 1
    assert results[0].title == "Buy milk"

@pytest.mark.asyncio
async def test_note_rag_loop():
    """Verify NoteManager RAG loop uses VectorStore and LLMClient correctly."""
    mock_vector = MagicMock()
    mock_vector.search_docs.return_value = [
        {"title": "Note 1", "content": "The secret code is 1234"}
    ]
    
    mock_llm = AsyncMock()
    mock_llm.generate_async.return_value = "The secret code is 1234."
    
    with patch("productivity.notes.LLMClient", return_value=mock_llm):
        manager = RagStore(vector_store=mock_vector)
        answer = await manager.query_notes("What is the secret code?")
        
        assert "1234" in answer
        mock_vector.search_docs.assert_called_once_with("What is the secret code?", limit=3)
        mock_llm.generate_async.assert_called_once()

@pytest.mark.asyncio
async def test_task_planner_persistence():
    """Verify TaskPlanner creates a chain and nodes in TreeStore."""
    from productivity.task_planner import TaskPlanner
    from productivity.models import TaskPlan, PlanStep
    
    mock_tree = MagicMock()
    mock_tree.create_chain.return_value = Chain(id=1, session_id="test")
    mock_tree.add_node.return_value = Node(id=101, chain_id=1, agent_role=AgentRole.ORCHESTRATOR, type=NodeType.PLAN)
    
    planner = TaskPlanner(tool_registry={}, tree_store=mock_tree)
    
    # Mock LLM response
    expected_plan = TaskPlan(
        id="plan-1",
        goal="Do something",
        steps=[PlanStep(action="Step 1")]
    )
    
    with patch("productivity.task_planner.generate_structured_output", AsyncMock(return_value=expected_plan)):
        await planner.create_plan("Do something", session_id="test_session")
        
        mock_tree.create_chain.assert_called_once_with(session_id="test_session", description="Do something")
        assert mock_tree.add_node.call_count == 1
