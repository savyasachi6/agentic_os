"""
agents/capability_agent.py
==========================
Refactored SQLAgentWorker (now CapabilityAgentWorker) using modular imports.
Handles SQL-based capability and tool discovery via the DB.
Depends on db.connection, db.queries.commands, db.models, core.types, and llm.client.
"""
import os
import asyncio
import re
import json
import logging
import traceback
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor

from llm.client import LLMClient
from db.connection import get_db_connection
from db.queries.commands import TreeStore
from db.models import Node
from core.types import AgentRole, NodeStatus
from agent_memory.cache import FractalCache # Temporarily

logger = logging.getLogger("agentos.agents.capability")

def _extract_sql_fallback(text: str) -> Optional[str]:
    """Fallback: extract a bare SQL statement from free-form LLM output."""
    match = re.search(
        r'(SELECT\b.+?;|SELECT\b.+?(?=\n\n|$)|INSERT\b.+?;|UPDATE\b.+?;|DELETE\b.+?;)',
        text, re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip().rstrip(';')
    return None

class CapabilityAgentWorker:
    """
    Background worker that handles `AgentRole.SCHEMA` (Capability) tasks.
    Queries the DB schema and available tools.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.cache = FractalCache()
        self.system_prompt = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Adjusted for modular architecture: llm/prompts/sql_agent_prompt.md
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "llm", "prompts", "sql_agent_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the CapabilityAgent (SQL). Discover tools and schema."

    def _execute_query(self, query: str) -> Dict[str, Any]:
        """Raw driver code to run the query safely."""
        try:
            with get_db_connection() as conn:
                try:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(query)
                        if cur.description:
                            rows = cur.fetchmany(100)
                            return {"success": True, "rows": [dict(r) for r in rows]}
                        else:
                            conn.commit()
                            return {"success": True, "message": "Executed successfully."}
                except Exception as e:
                    conn.rollback()
                    return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _process_task(self, task: Node):
        query_goal = task.payload.get("query", "Unknown Goal")
        print(f"[CapabilityAgent] Received Task {task.id}: {query_goal}")
        
        cached = await self.cache.get_cached_response_async(query_goal)
        if cached:
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result=cached["response"])
            return

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 5)
            for i in range(max_iterations):
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})
                
                from agent_core.loop.thought_loop import parse_react_action
                action_data = parse_react_action(response_text)
                if not action_data:
                    sql = _extract_sql_fallback(response_text)
                    if sql:
                        action_data = ("sql_query", sql)
                    else:
                        assert task.id is not None
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Parse error"})
                        return
                
                action_type, action_payload = action_data
                
                if action_type in ["complete", "done", "respond", "finish", "complete_task", "respond_direct"]:
                    # Unwrap JSON if the specialist returned a raw JSON string
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    asyncio.create_task(self.cache.set_cached_response_async(
                        query=query_goal, response={"message": final_res}, strategy_used="capability_worker"
                    ))
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": final_res})
                    return

                if action_type == "sql_query":
                    loop = asyncio.get_running_loop()
                    query_result = await loop.run_in_executor(None, self._execute_query, action_payload)
                    obs = f"Observation: {json.dumps(query_result, default=str)}"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Max iterations reached"})

        except Exception as e:
            logger.exception("CapabilityAgent error: %s", e)
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        print("[CapabilityAgent] Worker started.")
        while self._running:
            try:
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.SCHEMA)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("Polling error: %s", e)
                await asyncio.sleep(poll_interval)
