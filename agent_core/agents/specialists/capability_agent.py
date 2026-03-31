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

from agent_core.llm.client import LLMClient
from db.connection import get_db_connection
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.agent_types import Intent, AgentRole, NodeStatus
# Capability logic
from agent_core.reasoning import parse_react_action
from agent_core.agents.core.a2a_bus import A2ABus
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

CAPABILITY_FASTPATH = (
    "capabilities", "what can you do", "what are your capabilities",
    "tools", "inventory", "available agents", "how are we processing", "skills"
)

def is_capability_fastpath(query: str) -> bool:
    q = (query or "").lower().strip()
    return any(k in q for k in CAPABILITY_FASTPATH)

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
        self.role = AgentRole.SCHEMA
        self._running = False

    def _load_prompt(self):
        from agent_core.prompts import load_prompt
        try:
            self.system_prompt = load_prompt("agents", "capability")
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

    def _build_capability_manifest(self) -> str:
        """Phase 89: Accelerated manifest for capability queries."""
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT COUNT(*) as count FROM knowledge_skills")
                    skill_count = cur.fetchone()['count']
                    cur.execute("SELECT count(DISTINCT category) as count FROM knowledge_skills")
                    cat_count = cur.fetchone()['count']
            
            res = f"I am your Agentic OS, equipped with **{skill_count} specialized skills** across **{cat_count} categories**.\n\n"
            res += "### 🛠️ Core Toolsets\n"
            res += "- **Autonomous Research**: Multimodal RAG with semantic search over your local brain.\n"
            res += "- **SQL Engine**: Direct database introspection and capability mapping.\n"
            res += "- **Web Sandbox**: Live web search and browser manipulation via Playwright.\n"
            res += "- **Safe Execution**: Sandboxed Python environment for technical and data tasks.\n\n"
            res += "Use 'Sync Skills' in the UI to refresh my knowledge base."
            return res
        except Exception as e:
            logger.warning(f"Manifest failure: {e}")
            return "I am equipped for RAG, SQL Discovery, Web Search, and Code execution. I can help you search your knowledge base or interact with external tools."

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action
        import time
        start_time = time.time()
        query_goal = task.payload.get("query") or task.payload.get("goal") or "Unknown Goal"
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.SCHEMA.value}, goal='{query_goal[:50]}...'")
        
        # Restore selective static logic for specific project metadata (Phase 4 Maintenance)
        # Stricter: Only trigger if the query is short AND contains an explicit metadata intent.
        # This prevents hijacking complex "skills" questions that happen to mention documentation/github in context.
        query_lower = query_goal.lower().strip()
        is_metadata_ask = any(re.search(rf"\b{re.escape(p)}\b", query_lower) for p in ["links", "github", "repo", "documentation", "url"])
        is_concise = len(query_lower) < 60
        
        if is_metadata_ask and is_concise and "skills" not in query_lower and "build" not in query_lower:
            from agent_core.config import get_links_markdown
            logger.info(f"Link query detected. Returning static project links. node_id={task.id}")
            links_md = get_links_markdown()
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": links_md})
            return

        clean_goal = query_goal.lower().replace("?", "").replace(".", "").strip()

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]
        
        session_id = str(task.chain_id)
        
        # Phase 89: Capability Fast-Path
        if is_capability_fastpath(query_goal):
            logger.info("Capability Fast-Path triggered", extra={
                "event": "capability_fastpath", "node_id": task.id, "session_id": session_id
            })
            manifest = self._build_capability_manifest()
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": manifest, "source": "fastpath"})
            return

        sql_failures = 0

        try:
            max_iterations = task.payload.get("max_turns", 5)
            for i in range(max_iterations):
                # Check for abandonment (Phase 9 Hardening)
                current = await self.tree_store.get_node_by_id_async(task.id)
                if not current or current.status not in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    logger.warning(f"Task {task.id} abandoned by coordinator or failed elsewhere. Aborting specialist loop. node_id={task.id}")
                    return

                # Update status for UI visibility
                logger.info("Capability turn start", extra={
                    "event": "capability_turn_start", 
                    "node_id": task.id, 
                    "session_id": session_id,
                    "turn": i + 1,
                    "max_turns": max_iterations
                })
                response_text = await self.llm.generate_async(messages)
                
                # Extract native model thinking tokens
                import re as _re
                thinking_match = _re.search(r"<\|thinking\|>(.*?)(?:<\|/thinking\|>|$)", response_text, _re.DOTALL)
                if thinking_match:
                    native_thinking = thinking_match.group(1).strip()
                    response_text = _re.sub(r"<\|thinking\|>.*?(?:<\|/thinking\|>|$)", "", response_text, flags=_re.DOTALL).strip()
                    thought_text = native_thinking
                else:
                    from agent_core.reasoning import parse_thought
                    thought_text = parse_thought(response_text) if response_text else ""

                from agent_core.reasoning import normalize_thought
                
                if not hasattr(self, "_last_published_thought"):
                    self._last_published_thought = ""

                if thought_text:
                    clean_thought = normalize_thought(thought_text)
                    
                    if clean_thought and clean_thought != self._last_published_thought:
                        turn_label = f"**[Turn {i+1}/{max_iterations}]**\n\n"
                        await self.bus.publish(self.role.value, {
                            "type": "thought",
                            "content": turn_label + clean_thought,
                            "session_id": session_id
                        })
                        self._last_published_thought = clean_thought

                # Explicit Last Turn Nudge (Phase 87 Alignment)
                if i == max_iterations - 1:
                    messages.append({
                        "role": "user", 
                        "content": "CRITICAL: This is your LAST TURN. Based on the findings so far, provide a final BEST-EFFORT response to the goal. Do not call any more tools."
                    })

                if not response_text or response_text.strip() == "":
                    if thinking_match:
                        # Model is still thinking, provide a standard shim to encourage continuation
                        response_text = "[Reasoning in progress...]"
                    else:
                        logger.warning(f"LLM returned zero content and zero thinking. Turn {i+1}. node_id={task.id}")
                        if i == 0:
                            raise ValueError("LLM returned an empty response during schema discovery.")
                        response_text = "[Continuing...]"

                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    sql = _extract_sql_fallback(response_text)
                    if sql:
                        action_data = ("sql_query", sql)
                    else:
                        # Harden: Fallback to direct response if no Action was found
                        from agent_core.reasoning import strip_reasoning_markers
                        logger.info(f"No Action block found for capability query. Using direct response. node_id={task.id}")
                        cleaned = strip_reasoning_markers(response_text)
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": cleaned, "message": cleaned})
                        return
                
                action_type, action_payload = action_data
                logger.info("Capability action parsed", extra={
                    "event": "capability_action_parsed",
                    "role": self.role.value,
                    "node_id": task.id,
                    "session_id": session_id,
                    "turn": i + 1,
                    "action_type": action_type
                })
                
                if action_type in ["complete", "done", "respond", "finish", "complete_task", "respond_direct"]:
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info("Capability task completed", extra={
                        "event": "capability_task_done", "node_id": task.id, "session_id": session_id, "duration_ms": duration_ms
                    })
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": final_res, "message": final_res})
                    return

                if action_type == "sql_query":
                    loop = asyncio.get_running_loop()
                    query_result = await loop.run_in_executor(None, self._execute_query, action_payload)
                    
                    if not query_result.get("success"):
                        sql_failures += 1
                        if sql_failures >= 1:
                            logger.warning("SQL failure guard triggered. Falling back to manifest.", extra={
                                "event": "sql_guard_fallback", "node_id": task.id, "session_id": session_id, "error": query_result.get("error")
                            })
                            manifest = self._build_capability_manifest()
                            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": manifest, "source": "sql_guard"})
                            return
                            
                    obs = f"Observation: {json.dumps(query_result, default=str)}"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            duration = int((time.time() - start_time) * 1000)
            logger.warning("Max iterations reached", extra={
                "event": "max_turns",
                "role": self.role.value,
                "node_id": task.id,
                "session_id": str(task.chain_id),
                "duration_ms": duration
            })
            assert task.id is not None
            # Provide the last response as a partial success instead of a hard FAILED
            last_resp = messages[-1]["content"] if messages[-1]["role"] == "assistant" else "Max turns reached."
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"response": last_resp, "message": last_resp, "status": "partial_success"})

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            logger.error("Critical error in execution loop", extra={
                "event": "worker_error",
                "role": self.role.value,
                "node_id": task.id,
                "session_id": str(task.chain_id),
                "error_type": type(e).__name__,
                "duration_ms": duration
            }, exc_info=True)
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "critical_failure", "error": str(e)})

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
