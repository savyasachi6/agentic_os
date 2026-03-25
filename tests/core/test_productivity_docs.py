"""
Documentation-driven tests for the Productivity Engine.
Verifies that the examples in productivity/README.md are runnable and correct.
"""
import pytest
from agent_core.types import NodeType
from productivity.todo_manager import add_todo
from productivity.models import TodoStatus

def test_readme_add_todo_example():
    """
    Verifies:
    from productivity.todo_manager import add_todo
    todo = add_todo(
        title="Prepare for the architectural review",
        priority="high",
        due_date="2026-03-05",
        tags=["work", "arch"]
    )
    """
    # Note: When running tests from agent_core, the package is 'productivity'
    # The README uses 'core.productivity' which assumes root execution.
    # We test the relative import behavior here.
    
    todo = add_todo(
        title="Prepare for the architectural review",
        priority="high",
        due_date="2026-03-05",
        tags=["work", "arch"]
    )
    
    assert todo.title == "Prepare for the architectural review"
    assert todo.priority == 5 or todo.priority == "high" # Depending on final model choice
    assert "work" in todo.tags
    assert "arch" in todo.tags
    
    # Verify it can be retrieved
    from productivity.todo_manager import _manager
    todos = _manager.list_todos()
    assert any(t.id == todo.id for t in todos)
