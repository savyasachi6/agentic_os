"""
core/tools/registry.py
======================
Centralized tool registry for local Pydantic actions and external MCP tools.
"""

from typing import Dict, Any, Optional, List
from .base import BaseAction

class ToolRegistry:
    _instance: Optional['ToolRegistry'] = None

    def __init__(self):
        self.tools: Dict[str, BaseAction] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool: BaseAction):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseAction]:
        return self.tools.get(name)

    def list_tools(self) -> List[BaseAction]:
        return list(self.tools.values())

    def get_json_schemas(self) -> List[dict]:
        return [t.get_json_schema() for t in self.tools.values()]

registry = ToolRegistry.get_instance()
