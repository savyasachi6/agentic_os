import logging
import json
from typing import Dict, Any, List, Optional

from db.models import Node
from core.agent_types import AgentRole, NodeStatus
from core.message_bus import A2ABus
from db.queries.commands import TreeStore
from core.llm.client import LLMClient
from core.tool_registry import registry
from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.tool_caller")


class ToolCallerAgent:
    def __init__(self, llm_client: LLMClient = None):
        self.role = AgentRole.TOOL_CALLER
        self.llm = llm_client or LLMClient()
        self.bus = A2ABus()

    async def run(self, query: str, session_id: str = "tool_caller_session") -> Dict[str, Any]:
        """
        Execute tool-calling flow. Returns a dict with keys:
          - message: str  (human-readable answer)
          - tool_used: str | None
          - raw_result: Any
          - error: str | None
        """
        top_k_tools = registry.search_tools(query, top_k=5)

        if not top_k_tools:
            logger.warning("[tool_caller] No tools matched query: %s", query)
            return {
                "message": (
                    "I don't have the specific tools required for this request. "
                    "Available tools include scientific calculator and unit converter."
                ),
                "tool_used": None,
            }

        tool_names = [t["name"] for t in top_k_tools]
        tool_schemas = registry.get_ollama_schemas(tool_names)
        logger.info("[tool_caller] Tools selected: %s for query: %s", tool_names, query[:80])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise tool-calling assistant. "
                    "Map the user query to ONE of the provided tools. "
                    "Respond ONLY with the tool call JSON."
                ),
            },
            {"role": "user", "content": query},
        ]

        raw_response = await self.llm.generate_async(
            messages=messages,
            tools=tool_schemas,
            session_id=session_id,
        )

        tool_calls = _parse_tool_calls(raw_response)

        if not tool_calls:
            # LLM answered directly without calling a tool
            return {"message": raw_response or "No answer generated.", "tool_used": None}

        outputs = []
        for call in tool_calls:
            tool_name = call.get("function", {}).get("name", "")
            args = call.get("function", {}).get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            logger.info("[tool_caller] Invoking %s(%s)", tool_name, args)
            try:
                result = await registry.invoke(tool_name, **args)
                outputs.append({"tool": tool_name, "raw_result": result, "args": args})
            except Exception as e:
                logger.error("[tool_caller] Tool %s failed: %s", tool_name, e)
                outputs.append({"tool": tool_name, "error": str(e), "args": args})

        if not outputs:
            return {"message": "Tool execution produced no output.", "tool_used": None}

        first = outputs[0]
        if "error" in first:
            return {"message": f"Tool error: {first['error']}", "tool_used": first["tool"], "error": first["error"]}

        answer = str(first["raw_result"])
        return {
            "message": answer,
            "tool_used": first["tool"],
            "raw_result": first["raw_result"],
        }


def _parse_tool_calls(raw: str) -> List[Dict]:
    """Parse tool call JSON from LLM response. Handles [TOOL_CALL_DETECTED] prefix."""
    if not raw:
        return []
    if "[TOOL_CALL_DETECTED]" in raw:
        try:
            json_str = raw.split("[TOOL_CALL_DETECTED]")[1].strip()
            parsed = json.loads(json_str)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, IndexError) as e:
            logger.error("[tool_caller] Failed to parse TOOL_CALL_DETECTED JSON: %s", e)
    return []


class ToolCallerAgentWorker(AgentWorker):
    """
    Binds ToolCallerAgent to the AgentWorker A2ABus loop.
    Correctly updates node lifecycle via tree_store.
    """
    def __init__(self, store: TreeStore = None):
        self._tool_agent = ToolCallerAgent()
        super().__init__(role=AgentRole.TOOL_CALLER, agent=self._tool_agent, store=store or TreeStore())

    async def _process_task(self, task: Node):
        query = task.payload.get("query") or task.payload.get("goal") or task.content or ""
        session_id = getattr(task, "session_id", None) or str(task.chain_id)

        logger.info("[tool_caller] Processing node %s: %s", task.id, query[:80])

        result = await self._tool_agent.run(query=query, session_id=session_id)

        if result.get("error"):
            await self.tree_store.update_node_status_async(
                task.id,
                NodeStatus.FAILED,
                result={"error_type": "tool_error", "error": result["error"]},
            )
            return

        await self.tree_store.update_node_status_async(
            task.id,
            NodeStatus.DONE,
            result={"message": result["message"], "tool_used": result.get("tool_used")},
        )
