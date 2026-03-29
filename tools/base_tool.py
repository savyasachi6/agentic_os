from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseTool(ABC):
    """Abstract interface enforcing strict definition contracts for system tools."""
    name: str = ""
    description: str = ""
    parameters_schema: Dict[str, Any] = {}

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Executes the tool logic with the provided keyword arguments."""
        pass
        
    def get_schema(self) -> Dict[str, Any]:
        """Returns the OpenAI-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }
