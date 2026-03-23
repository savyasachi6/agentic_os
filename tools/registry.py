# tools/registry.py
import importlib
import inspect
import os
import pkgutil
from typing import Dict, Type, Optional
from .base_tool import BaseTool

class ToolRegistry:
    """
    Central registry for all tools.
    Supports auto-discovery of tools in specified directories.
    """
    _instance: Optional['ToolRegistry'] = None

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tool(self, tool: BaseTool):
        self.tools[tool.name] = tool
        print(f"[Registry] Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name.lower())

    def list_tools(self) -> Dict[str, str]:
        return {name: tool.description for name, tool in self.tools.items()}

    def discover_tools(self, package_path: str):
        """
        Recursively discover and register all subclasses of BaseTool in the given package.
        """
        package_dir = os.path.dirname(package_path)
        package_name = os.path.basename(package_dir)
        
        for loader, module_name, is_pkg in pkgutil.walk_packages([package_dir], f"{package_name}."):
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        # Instantiate and register
                        tool_instance = obj()
                        self.register_tool(tool_instance)
            except Exception as e:
                print(f"[Registry] Error loading module {module_name}: {e}")

# Global registry instance
registry = ToolRegistry.get_instance()

def register_tool(cls):
    """Decorator to register a tool class."""
    registry.register_tool(cls())
    return cls
