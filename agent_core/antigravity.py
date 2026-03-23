# agent_core/antigravity.py
"""
Antigravity Framework - Light-weight tool and agent registration system.
"""
import functools
import inspect
from typing import Any, Callable, Dict, Type, Optional

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, func: Callable):
        self.tools[name] = {
            "name": name,
            "description": description,
            "func": func,
            "signature": inspect.signature(func)
        }

def tool(name: str = None, description: str = None):
    """Decorator to mark a method as an agent tool."""
    def decorator(func: Callable):
        func._is_tool = True
        func._tool_name = name or func.__name__
        func._tool_description = description or func.__doc__ or ""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def agent(name: str = None):
    """Decorator to mark a class as an agent."""
    def decorator(cls: Type):
        cls._is_agent = True
        cls._agent_name = name or cls.__name__
        return cls
    return decorator
