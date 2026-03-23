"""
Tests for the Personal Productivity module.
"""
from datetime import datetime
from agent_productivity.todo_manager import TodoManager
from agent_productivity.briefing import generate_briefing, format_briefing
from agent_productivity.models import TodoItem, TodoStatus


def test_todo_manager_crud():
    manager = TodoManager()
    todo = manager.add_todo("Test task", priority=3)
    assert todo.title == "Test task"
    assert todo.priority == 3
    assert len(manager.list_todos()) == 1
    
    manager.update_status(todo.id, TodoStatus.COMPLETED)
    assert manager.list_todos(status=TodoStatus.COMPLETED)[0].id == todo.id


def test_briefing_generation():
    manager = TodoManager()
    due_todo = manager.add_todo("Due today", due_date=datetime.now())
    
    briefing = generate_briefing(datetime.now(), [due_todo], [])
    assert len(briefing.todos_due) == 1
    
    fmt = format_briefing(briefing)
    assert "Due today" in fmt
    assert "Weather" in fmt


def test_todo_search():
    manager = TodoManager()
    manager.add_todo("Buy milk")
    manager.add_todo("Write code")
    
    results = manager.search_todos("milk")
    assert len(results) == 1
    assert results[0].title == "Buy milk"
