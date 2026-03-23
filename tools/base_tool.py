# tools/base_tool.py
import abc
import json
from typing import Dict, Any, List
from db.commands import log_event

class BaseTool(abc.ABC):
    """
    Abstract base class for all tools.
    Encapsulates execution logic, payload validation, and event logging.
    """
    def __init__(self):
        self.name: str = self.__class__.__name__.lower()
        self.description: str = ""
        self.risk_level: str = "normal"  # low | normal | high
        self.tags: List[str] = []

    @abc.abstractmethod
    async def run(self, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Tool execution logic. MUST be implemented by subclasses."""
        pass

    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Override to provide custom payload validation."""
        return True

    async def log_execution(self, session_id: str, payload: Dict[str, Any], result: Dict[str, Any]):
        """Helper to log tool execution to the events table."""
        await log_event(session_id, f"tool_execution_{self.name}", {
            "payload": payload,
            "result": result,
            "risk_level": self.risk_level
        })
