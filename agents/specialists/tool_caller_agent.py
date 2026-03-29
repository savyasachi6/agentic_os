import logging
import json
from typing import Dict, Any, List

from db.models import Node
from core.agent_base import AgentResponse
from core.agent_types import AgentRole, NodeStatus
from core.message_bus import A2ABus
from db.queries.commands import TreeStore
from core.llm.client import LLMClient
from core.tool_registry import registry
from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.tool_caller")

class ToolCallerAgent:
    """
    Agent that acts as the Planner/Executor for dynamic tools.
    Receives a user query, scopes the tools, calls Ollama with 'tools=...',
    and executes the native python functions locally.
    """
    def __init__(self, llm_client: LLMClient = None):
        self.role = AgentRole.TOOL_CALLER
        self.llm = llm_client or LLMClient()
        self.bus = A2ABus()

    async def _process_task(self, task: Node):
        """Standard entry point for AgentWorker."""
        payload = task.payload
        chain_id = task.chain_id
        query = payload.get("query", task.content or "")
        
        # 1. Search the registry for Top-K candidate tools
        # Phase 48 Hardening: Explicitly log tool counts
        top_k = registry.search_tools(query, top_k=5)
        
        if not top_k:
            logger.warning(f"[{self.role}] No tools matched query: {query}")
            # Phase 50: Return a cleaner string so 'Status Autopilot' marks it DONE
            return "I'm sorry, I don't have the specific mathematical or scientific tools enabled to answer that right now."
        
        # 2. Extract schemas for Ollama
        tool_names = [t["name"] for t in top_k]
        tool_schemas = registry.get_ollama_schemas(tool_names)
        
        logger.info(f"[{self.role}] Retrieved {len(tool_schemas)} tools ({tool_names}) for query: {query}")
        
        # 3. Call the LLM with the tool schemas via the hardened public API
        messages = [
            {"role": "system", "content": "You are a precise tool-calling assistant. Your only purpose is to map user queries to the registered tools provided. Only call the provided functions. If a tool is called, respond ONLY with the tool call JSON."},
            {"role": "user", "content": query}
        ]

        # Phase 4.2: Use unified generate_async with tools
        raw_response = await self.llm.generate_async(
            messages=messages,
            tools=tool_schemas,
            session_id=task.session_id or "tool_caller_session"
        )

        # 4. Parse the tool calls from the unified response
        # Our backends wrap tool calls in [TOOL_CALL_DETECTED] prefix when sent through the router
        tool_calls = []
        if "[TOOL_CALL_DETECTED]" in raw_response:
            try:
                json_str = raw_response.split("[TOOL_CALL_DETECTED]")[1].strip()
                tool_calls = json.loads(json_str)
            except Exception as e:
                logger.error(f"[{self.role}] Failed to parse tool call JSON: {e}")
        
        # Check if the LLM actually called a tool
        if not tool_calls:
            return {"response": raw_response, "message": "The assistant decided not to call a tool or returned a direct answer."}

        # 5. Execute the mapped Python function locally
        outputs = []
        for call in tool_calls:
            tool_name = call["function"]["name"]
            try:
                args = call["function"]["arguments"]
            except Exception:
                args = {}

            logger.info(f"[{self.role}] Invoking {tool_name}({args})")
            
            try:
                # registry.invoke handles async/sync natively safely
                result = await registry.invoke(tool_name, **args)
                outputs.append({"tool": tool_name, "raw_result": result, "args": args})
                logger.info(f"[{self.role}] Tool Output: {result}")
            except Exception as e:
                logger.error(f"[{self.role}] Tool Execution Error: {e}")
                outputs.append({"tool": tool_name, "error": str(e), "args": args})

        # Return structured output
        # For a single tool execution, just return the first result directly
        if len(outputs) == 1 and "raw_result" in outputs[0]:
            ans = str(outputs[0]["raw_result"])
            return {"response": ans, "message": ans, "raw_result": outputs[0]["raw_result"], "tool_used": outputs[0]["tool"]}

        return {"response": "Processed tool requests.", "details": outputs}

class ToolCallerAgentWorker(AgentWorker):
    """
    Subclasses the generic AgentWorker to bind the ToolCallerAgent to the A2ABus loop.
    """
    def __init__(self, store: TreeStore = None):
        agent = ToolCallerAgent()
        super().__init__(role=AgentRole.TOOL_CALLER, agent=agent, store=store)
