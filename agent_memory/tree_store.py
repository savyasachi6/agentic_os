"""
agent_memory/tree_store.py (COMPATIBILITY SHIM)
==============================================
This file exists for backward compatibility during the architecture refactor.
The TreeStore logic has been moved to: db/queries/commands.py

Do not add new methods here. Import from db.queries.commands directly.
"""
from db.queries.commands import TreeStore

__all__ = ["TreeStore"]
