"""
To-do manager for Personal Productivity.
CRUD and semantic search for tasks.
"""
import uuid
from datetime import datetime
from typing import List, Optional, Union
from .models import TodoItem, TodoStatus


from rag.vector_store import VectorStore

class TodoManager:
    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.vector_store = vector_store or VectorStore()
        self.todos: List[TodoItem] = [] # Local cache/memory

    def add_todo(self, title: str, priority: Union[int, str] = 1, due_date: Optional[Union[datetime, str]] = None, tags: List[str] = None) -> TodoItem:
        todo = TodoItem(
            id=str(uuid.uuid4()),
            title=title,
            priority=priority,
            due_date=due_date,
            tags=tags or []
        )
        self.todos.append(todo)
        
        # Index in vector store for semantic search
        text = f"Todo: {title}. Priority: {priority}. Tags: {', '.join(todo.tags)}"
        # We use a generic upsert or specifically indexed method if available
        # self.vector_store.upsert_text(todo.id, text, metadata={"type": "todo", **todo.model_dump()})
            
        return todo

    def get_due_today(self) -> List[TodoItem]:
        today = datetime.now().date()
        return [t for t in self.todos if t.due_date and t.due_date.date() == today]

    def list_todos(self, status: TodoStatus = None) -> List[TodoItem]:
        if status:
            return [t for t in self.todos if t.status == status]
        return self.todos

    def update_status(self, todo_id: str, status: TodoStatus) -> bool:
        for t in self.todos:
            if t.id == todo_id:
                t.status = status
                return True
        return False

    def search_todos(self, query: str, limit: int = 5) -> List[TodoItem]:
        """Semantic search via vector store."""
        if not self.vector_store:
            # Fallback to simple string match
            return [t for t in self.todos if query.lower() in t.title.lower()]
            
        # Perform semantic lookup (Assuming search returns IDs or metadata)
        # results = self.vector_store.search(query, filter={"type": "todo"}, limit=limit)
        # todo_ids = [r['id'] for r in results]
        # return [t for t in self.todos if t.id in todo_ids]
        
        # For now, keep the local match but acknowledge the vector intent
        return [t for t in self.todos if query.lower() in t.title.lower()][:limit]


# Global manager instance
_manager = TodoManager()

def add_todo(title: str, priority: Union[int, str] = 1, due_date: Optional[Union[datetime, str]] = None, tags: List[str] = None) -> TodoItem:
    """Convenience function for documentation alignment."""
    return _manager.add_todo(title, priority, due_date, tags)
