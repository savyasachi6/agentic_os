# router/tool_router.py
from typing import Dict, Any, Optional
from tools.registry import registry
from tools.base_tool import BaseTool
from .risk_gate import RiskGate

class ToolRouter:
    """
    Unifies local and external (MCP) tools.
    Handles tool discovery, routing, and risk-gated execution.
    """
    def __init__(self):
        self.risk_gate = RiskGate()

    async def dispatch(self, tool_name: str, payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Route tool call to the correct implementation."""
        print(f"[Router] Dispatching tool: {tool_name}")
        
        tool = registry.get_tool(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found in registry."}

        # 1. Validate payload
        if not tool.validate_payload(payload):
            return {"error": f"Invalid payload for tool '{tool_name}'"}

        # 2. Check risk gate
        approved, message = await self.risk_gate.check(tool, payload, session_id)
        if not approved:
            return {"error": f"Risk gate blocked tool '{tool_name}': {message}", "status": "blocked"}

        # 3. Execute tool
        try:
            return await tool.run(payload, session_id)
        except Exception as e:
            return {"error": f"Error executing tool '{tool_name}': {str(e)}"}

# Global tool router instance
tool_router = ToolRouter()
