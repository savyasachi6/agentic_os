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
from agent_core.graph.state import AgentState
from agent_core.agent_types import Intent, AgentRole, NodeStatus
# Capability logic
from agent_core.reasoning import parse_react_action
from agents.a2a_bus import A2ABus
from agent_core.config import get_links_markdown

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
        self.system_prompt = ""
        self._load_prompt()
        self.bus = A2ABus()
        self._running = False

    def _load_prompt(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "assets", "prompts", "capability.md")
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
        from agent_core.reasoning import parse_react_action
        import time
        start_time = time.time()
        query_goal = task.payload.get("query", "Unknown Goal")
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.SCHEMA.value}, goal='{query_goal[:50]}...'")
        
        # Immediate shortcut for project links
        link_keywords = ["links", "url", "github", "repo", "documentation", "where is the code"]
        if any(kw in query_goal.lower() for kw in link_keywords):
            logger.info(f"Link query detected. Returning structured project links. node_id={task.id}")
            links_md = get_links_markdown()
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": links_md})
            return

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 5)
            for i in range(max_iterations):
                logger.info(f"Turn {i+1}/{max_iterations}: Starting LLM generation...")
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    sql = _extract_sql_fallback(response_text)
                    if sql:
                        action_data = ("sql_query", sql)
                    else:
                        duration = time.time() - start_time
                        logger.error(f"Parse error. node_id={task.id}, duration={duration:.2f}s")
                        assert task.id is not None
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Parse error"})
                        return
                
                action_type, action_payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")
                
                if action_type in ["complete", "done", "respond", "finish", "complete_task", "respond_direct"]:
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    duration = time.time() - start_time
                    logger.info(f"Task completed. node_id={task.id}, duration={duration:.2f}s")
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
                
            duration = time.time() - start_time
            logger.warning(f"Max iterations reached. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Max iterations reached"})

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Critical error in execution loop: {e}. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self):
        self._running = True
        logger.info(f"CapabilityAgentWorker started (listening on A2A bus topic: {AgentRole.SCHEMA.value})")
        
        async for msg in self.bus.listen(AgentRole.SCHEMA.value):
            if not self._running:
                break
            try:
                node_id = msg.get("node_id")
                if node_id:
                    task = self.tree_store.get_node_by_id(node_id)
                    if task:
                        await self._process_task(task)
            except Exception as e:
                logger.error(f"Error processing A2A message: {e}")
