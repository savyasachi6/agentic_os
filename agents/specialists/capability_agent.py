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

from core.llm.client import LLMClient
from db.connection import get_db_connection
from db.queries.commands import TreeStore
from db.models import Node
from agents.graph.state import AgentState
from core.agent_types import Intent, AgentRole, NodeStatus
# Capability logic
from core.reasoning import parse_react_action
from core.message_bus import A2ABus
from core.settings import settings, get_links_markdown
from core.tool_registry import registry

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

from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.capability")

class CapabilityAgentWorker(AgentWorker):
    """
    Background worker that handles task decomposition and system discovery (AgentRole.SCHEMA).
    """
    def __init__(self, store: TreeStore = None, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.role = AgentRole.SCHEMA
        self.system_prompt = ""
        self._load_prompt()
        
        # Initialize parent worker with this role and current instance as the agent
        super().__init__(role=self.role, agent=self, store=store or TreeStore())

    def _load_prompt(self):
        from prompts.loader import load_prompt
        try:
            self.system_prompt = load_prompt("capability")
        except Exception as e:
            logger.error(f"Failed to load capability prompt: {e}")
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
        import time
        start_time = time.time()
        query_goal = task.payload.get("query") or task.payload.get("goal") or "Unknown Goal"
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.SCHEMA.value}, goal='{query_goal[:50]}...'")
        
        # Restore selective static logic for specific project metadata (Phase 4 Maintenance)
        # Expanded to handle 'What can you do?' and capability discovery.
        query_lower = query_goal.lower().strip()
        metadata_patterns = [
            r"\blinks\b", r"\bgithub\b", r"\brepo\b", r"\bdocumentation\b", r"\bsource code\b", r"\burl\b", 
            r"\bwhat can you do\b", r"\bwhat are you\b", r"\bwho are you\b", r"\bhow do you work\b", r"\byour flow\b",
            r"\bcapabilities\b", r"\bfeatures\b", r"\bi can help\b", r"\bhelp me\b", r"\bskills\b",
            r"\beverything\b", r"\byou have\b", r"\bour system\b"
        ]
        is_metadata_ask = any(re.search(p, query_lower) for p in metadata_patterns)
        is_concise = len(query_lower) < 100 
        
        # If it's a pure metadata/links/capability ask, return immediately with a manifest
        if is_metadata_ask and is_concise:
            logger.info(f"Capability query detected. Generating dynamic manifest. node_id={task.id}")
            
            # 1. Fetch live system stats
            roles = [r.value for r in AgentRole]
            tools = registry.list_tools()
            
            skill_count = 0
            # Explicit SQL call for skills count (Dynamic Phase)
            res = self._execute_query("SELECT COUNT(*) as count FROM knowledge_skills WHERE deleted_at IS NULL")
            if res.get("success") and res.get("rows"):
                skill_count = res["rows"][0]["count"]
            
            # 2. Formulate a 'Conciege Context' for the LLM
            stats = {
                "active_specialist_roles": roles,
                "registered_tool_count": len(registry.tools),
                "registered_tool_names": list(registry.tools.keys())[:10], # Truncated for prompt efficiency
                "total_skills_indexed": skill_count,
                "project_links": get_links_markdown()
            }
            
            # 3. Generate a dynamic, unique persona response via LLM (Single-Turn)
            messages = [
                {"role": "system", "content": "You are the Agentic OS Digital Concierge. Present the following system stats in a unique, conversational, and high-energy way. Vary your tone and don't provide a robotic list. Focus on different strengths if the user asks repeatedly. Use Markdown. BE CONCISE."},
                {"role": "user", "content": f"System Stats: {json.dumps(stats)}\n\nUser Question: {query_goal}"}
            ]
            
            summary = ""
            async for chunk in self.llm.generate_streaming(messages, session_id=str(task.chain_id)):
                if chunk.get("type") == "token":
                    summary += chunk.get("content", "")
                    await self.bus.publish(self.role.value, {"type": "token", "content": chunk.get("content", "")})
            
            if not summary.strip():
                summary = "I am Agentic OS. I am online and ready to assist with research, code, and scheduling."
            
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": summary, "message": summary})
            return

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 5)
            for i in range(max_iterations):
                # Check for abandonment
                current = await self.tree_store.get_node_by_id_async(task.id)
                if not current or current.status not in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    logger.warning(f"Task {task.id} abandoned. node_id={task.id}")
                    return

                # Update status for UI visibility
                logger.info(f"Turn {i+1}/{max_iterations}: Starting Capability streaming...")
                
                response_text = ""
                turn_label = f"**[Capability Turn {i+1}/{max_iterations}]** "
                first_thought = True

                async for chunk in self.llm.generate_streaming(messages, session_id=str(task.chain_id)):
                    chunk_type = chunk.get("type")
                    content = chunk.get("content", "")
                    
                    if chunk_type == "thought":
                        if first_thought and content:
                            content = turn_label + content
                            first_thought = False
                        
                        await self.bus.publish(self.role.value, {"type": "thought", "content": content})
                    elif chunk_type == "token":
                        response_text += content
                        await self.bus.publish(self.role.value, {"type": "token", "content": content})
                    elif chunk_type == "error":
                        logger.error(f"Streaming error: {content}")
                        break

                if not response_text or not response_text.strip():
                    logger.warning(f"LLM returned no content on turn {i+1}. node_id={task.id}")
                    # Phase 5.1: Defensive turn retry
                    if i < 3: # Allow retries on early turns
                        await self.bus.publish(self.role.value, {
                            "type": "thought", 
                            "content": f"System is waiting for a more complete response on turn {i+1}... (Retrying)"
                        })
                        await asyncio.sleep(3)
                        continue
                    else:
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "no_content", "error": f"LLM failed to produce content on turn {i+1} after retries."})
                        return

                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    sql = _extract_sql_fallback(response_text)
                    if sql:
                        action_data = ("sql_query", sql)
                    else:
                        from core.reasoning import strip_all_reasoning
                        logger.info(f"Using direct response for capability query. node_id={task.id}")
                        cleaned = strip_all_reasoning(response_text)
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": cleaned, "message": cleaned})
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
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": final_res, "message": final_res})
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
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "max_turns", "error": "Max iterations reached without completing."})

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Critical error in execution loop: {e}. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "critical_failure", "error": str(e)})

    # run_forever removed in Phase 5: Now managed by AgentWorker backbone.
