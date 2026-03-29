"""
core/tools/base.py
==================
Base models for the Pydantic-based action system.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel

class ActionResult(BaseModel):
    success: bool
    data: Dict[str, Any]
    error_trace: Optional[str] = None
    suggested_retry: bool = False

class BaseAction(BaseModel):
    """Abstract base class for all AI tools"""
    name: str = ""
    description: str = ""
    risk_level: str = "low"
    parameters: str = ""

    def get_json_schema(self) -> dict:
        """Auto-syncs python arguments to Ollama/LangGraph tool schemas!"""
        return self.model_json_schema()

    async def run_action_async(self, **kwargs) -> ActionResult:
        """Asynchronous execution returning an ActionResult (for MCP/Network tools)."""
        try:
            # Pydantic validation
            validated_instance = self.__class__(**kwargs)
            if hasattr(validated_instance, 'run_async'):
                result = await validated_instance.run_async()
            else:
                result = validated_instance.run()
            return ActionResult(success=True, data={"output": result})
        except Exception as e:
            return ActionResult(success=False, data={}, error_trace=str(e), suggested_retry=True)

    def run_action(self, **kwargs) -> ActionResult:
        """Strictly typed synchronous execution."""
        try:
            validated_instance = self.__class__(**kwargs)
            result = validated_instance.run()
            return ActionResult(success=True, data={"output": result})
        except Exception as e:
            return ActionResult(success=False, data={}, error_trace=str(e), suggested_retry=True)
            
    def run(self) -> Any:
        raise NotImplementedError
