from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from core.llm.client import LLMClient
from core.tool_registry import ToolRegistry

class AgentResponse(BaseModel):
    """Standardized response envelope for all agentic operations."""
    status: str
    content: str
    metadata: Dict[str, Any]

class BaseAgent(ABC):
    """Abstract foundational class for all specialized and orchestration agents."""
    
    name: str = "BaseAgent"
    description: str = "Abstract agent"
    system_prompt: str = ""
    
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self.llm = llm_client
        self.tools = tool_registry
        self.memory: List[Dict[str, str]] = [{"role": "system", "content": getattr(self, "system_prompt", "")}]

    @abstractmethod
    async def run(self, task: str) -> AgentResponse:
        """The primary execution loop to be implemented by subclass agents."""
        pass
        
    async def _invoke_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> Any:
        """Internal helper to delegate execution to the unified registry."""
        return await self.tools.invoke(tool_name, **kwargs)
