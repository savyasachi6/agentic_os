"""
agents/tools/specialist_tools.py
===============================
Exposes modular agents as LangChain tools for reuse in graphs and agents.
"""
import logging
from typing import Dict, Any, Optional
from langchain_core.tools import StructuredTool
from agent_core.types import AgentRole

logger = logging.getLogger("agentos.agents.tools.specialist")

def make_specialist_tool(bridge_agent, name: str, description: str):
    """
    Wraps a BridgeAgent into a LangChain StructuredTool.
    
    Args:
        bridge_agent: The BridgeAgent instance to wrap.
        name: Tool name.
        description: Tool description for the LLM.
    """
    async def _run(goal: str) -> str:
        # Specialist agents are invoked via the BridgeAgent.execute method
        # which writes to the TreeStore and waits for a worker to finish.
        # We assume chain_id=0 for generic tool calls if not provided.
        result = await bridge_agent.execute({"goal": goal}, chain_id=0)
        
        if "error" in result:
             return f"Tool Error: {result['error']}"
        
        return result.get("message", str(result))
    
    return StructuredTool.from_function(
        coroutine=_run,
        name=name,
        description=description,
    )
