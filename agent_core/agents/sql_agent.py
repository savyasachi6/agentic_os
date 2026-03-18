import os
import asyncio
import re
import time
import json
import traceback
from typing import Optional

from psycopg2.extras import RealDictCursor

from agent_core.llm import LLMClient
from agent_memory.db import get_db_connection
from agent_memory.tree_store import TreeStore
from agent_memory.models import Node, AgentRole, NodeStatus
from agent_memory.cache import FractalCache
from agent_core.loop.thought_loop import parse_react_action


def _extract_sql_fallback(text: str) -> Optional[str]:
    """Fallback: extract a bare SQL statement from free-form LLM output."""
    # Look for common SQL statement starts (case-insensitive)
    match = re.search(
        r'(SELECT\b.+?;|SELECT\b.+?(?=\n\n|$)|INSERT\b.+?;|UPDATE\b.+?;|DELETE\b.+?;)',
        text, re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip().rstrip(';')
    return None


class SQLAgentWorker:
    """
    Background worker that polls the central Tree Store for `AgentRole.SCHEMA` nodes.
    It reads the DB Schema, writes queries safely, and returns the fetched rows 
    to the Coordinator Agent.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.cache = FractalCache()
        self.system_prompt = "" # Ensure it exists
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Use relative pathing from this file to ensure it works across different root_dir guesses
        this_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(os.path.dirname(this_dir), "prompts", "sql_agent_prompt.md")
        
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the SQLAgentWorker. Execute queries safely."

    def _execute_query(self, query: str) -> dict:
        """Raw driver code to run the query against the pgvector DB safely."""
        try:
            with get_db_connection() as conn:
                try:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(query)
                        
                        if cur.description:
                            # Fetch up to 100 rows to prevent blowing out context
                            rows = cur.fetchmany(100)
                            return {"success": True, "rows": [dict(r) for r in rows]}
                        else:
                            conn.commit()
                            return {"success": True, "message": "Command executed successfully. No rows returned."}
                except Exception as e:
                    conn.rollback()
                    return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _process_task(self, task: Node):
        """ReAct reasoning specific entirely to the SQL Agent's payload context."""
        query_goal = task.payload.get("query", "Unknown Goal")
        print(f"[SQLAgent] Received Task {task.id}: {query_goal}")
        
        # 1. First check Fractal Cache to bypass execution if exact/semantic match 
        cached = self.cache.get_cached_response(query_goal)
        if cached:
            print(f"[SQLAgent] Hit FractalCache! Strategy: {cached.get('strategy')}. Resolving instantly.")
            self.tree_store.update_node_status(task.id, NodeStatus.DONE, result=cached["response"])
            return

        # 2. Build local prompt loop
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task Goal: {query_goal}\n\nPayload Constraints: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 3)
            for i in range(max_iterations):
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    # Fallback: maybe the LLM emitted SQL directly without the Action: wrapper
                    sql = _extract_sql_fallback(response_text)
                    if sql:
                        print(f"[SQLAgent] Fallback SQL extracted: {sql[:80]}")
                        action_data = ("sql_query", sql)
                    else:
                        print(f"[SQLAgent] ERROR: Failed to output ReAct action loop correctly. Raw output:\n{response_text}")
                        self.tree_store.update_node_status(task.id, NodeStatus.FAILED, result={"error": "Failed to output ReAct action loop correctly"})
                        return
                
                action_type, action_payload = action_data
                
                if action_type in ["complete", "complete_task", "done", "respond", "finish"]:
                    # Cache asynchronously — avoids blocking the shared uvicorn event loop
                    asyncio.create_task(self.cache.set_cached_response_async(
                        query=query_goal,
                        response={"message": action_payload},
                        strategy_used="sql_worker"
                    ))
                    
                    self.tree_store.update_node_status(task.id, NodeStatus.DONE, result={"message": action_payload})
                    print(f"[SQLAgent] Finished task {task.id}")
                    return

                if action_type == "sql_query":
                    print(f"[SQLAgent] Executing: {action_payload}")
                    query_result = self._execute_query(action_payload)
                    obs = f"Observation: {json.dumps(query_result, default=str)}"
                    messages.append({"role": "user", "content": obs})
                else:
                    messages.append({"role": "user", "content": f"Observation: Unknown action type {action_type}"})
                    
            self.tree_store.update_node_status(task.id, NodeStatus.FAILED, result={"error": "Too many execution iterations without returning."})

        except Exception as e:
            traceback.print_exc()
            self.tree_store.update_node_status(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        """Infinite loop polling queue for 'sql' tasks."""
        self._running = True
        print("[SQLAgent] Worker started.")
        while self._running:
            try:
                task = self.tree_store.dequeue_task(agent_role=AgentRole.SCHEMA)

                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                print(f"[SQLAgent] Polling error: {e}")
                await asyncio.sleep(poll_interval)
