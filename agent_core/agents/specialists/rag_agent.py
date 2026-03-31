"""
agents/rag_agent.py
===================
Refactored ResearcherAgentWorker (now RAGAgentWorker) using modular imports.
Handles hybrid search, speculative RAG, and web fetching.
Depends on db.queries.commands, db.models, core.types, and llm.client.
"""
import os
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List

from agent_core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.agent_types import NodeType, AgentRole, AgentResult, NodeStatus
# RAG logic
from agent_core.rag.cognitive_retriever import CognitiveRetriever
from core.message_bus import A2ABus

# Sandbox tools temporarily disabled until moved to core/sandbox
PLAYWRIGHT_AVAILABLE = False
handle_browser_navigate = None
ToolCallRequest = None

logger = logging.getLogger("agentos.agents.rag")

class ResearchAgentWorker:
    """
    Background worker that polls for `AgentRole.RAG` nodes.
    Performs information retrieval and synthesis.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.retriever = CognitiveRetriever()
        self.bus = A2ABus()
        self.role = AgentRole.RAG
        self.system_prompt = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        from agent_core.prompts import load_prompt
        try:
            self.system_prompt = load_prompt("agents", "rag")
        except Exception as e:
            logger.error(f"Failed to load RAG prompt: {e}")
            self.system_prompt = "You are the RAGAgent. Perform research and retrieval."

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action, parse_thought
        import time
        start_time = time.time()
        import re
        query_goal = task.payload.get("query") or task.payload.get("goal") or "Unknown Goal"
        session_id = str(task.chain_id)
        research_keywords = [
            r"research", 
            r"search", 
            r"find", 
            r"lookup", 
            r"query", 
            r"who", 
            r"what (is|are)", 
            r"how do i"
        ]
        clean_goal = query_goal.lower().replace("?", "").replace(".", "").strip()
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.RAG.value}, goal='{query_goal[:50]}...'")
        
        current_date = datetime.now().strftime("%B %d, %Y")
        system_content = self.system_prompt.replace("{current_date}", current_date)
        if "Today is" not in system_content:
            system_content = f"Today is {current_date}.\n\n" + system_content

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Task Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]

        try:
            max_iterations = task.payload.get("max_turns", 4)
            for i in range(max_iterations):
                # Check for abandonment (Phase 9 Hardening)
                current_node = await self.tree_store.get_node_by_id_async(task.id)
                if not current_node or current_node.status not in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    logger.warning(f"Task {task.id} abandoned by coordinator. Aborting research turn. node_id={task.id}")
                    return

                # Update status for UI visibility (Phase 5 Hardening)
                status_msg = f"Reasoning Turn {i+1}/{max_iterations}..."
                assert task.id is not None
                await self.tree_store.update_node_status_async(task.id, NodeStatus.PENDING, result={"progress": status_msg})

                logger.info(f"{status_msg} Starting LLM generation...")
                response_text = await self.llm.generate_async(messages, session_id=session_id)
                
                # Extract native model thinking tokens if present (qwen3-vl:8b / thinking models)
                # Harden: handle unclosed tags due to truncation
                import re as _re
                thinking_match = _re.search(r"<\|thinking\|>(.*?)(?:<\|/thinking\|>|$)", response_text, _re.DOTALL)
                if thinking_match:
                    native_thinking = thinking_match.group(1).strip()
                    # Remove the entire thinking block from the response for downstream parsing
                    response_text = _re.sub(r"<\|thinking\|>.*?(?:<\|/thinking\|>|$)", "", response_text, flags=_re.DOTALL).strip()
                    thought_text = native_thinking
                else:
                    thought_text = parse_thought(response_text)
                
                if thought_text and thought_text.strip():
                    turn_label = f"**[Turn {i+1}/{max_iterations}]**\n\n"
                    await self.bus.publish(self.role.value, {
                        "type": "thought",
                        "content": turn_label + thought_text,
                        "session_id": session_id
                    })

                if not response_text or response_text.strip() == "":
                    if thinking_match:
                        # Model is still thinking, provide a standard shim for continuation
                        response_text = "[Research reasoning in progress...]"
                    else:
                        logger.warning(f"LLM returned zero content and zero thinking. Turn {i+1}. node_id={task.id}")
                        if i == 0:
                            raise ValueError("LLM returned a completely empty response. Possible timeout or context window issue.")
                        response_text = "[Continuing research...]"


                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                
                rl_meta = task.payload.get("rl_metadata", {})

                if not action_data:
                    from agent_core.reasoning import strip_reasoning_markers
                    duration = time.time() - start_time
                    logger.info(f"No action parsed. Completing task. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(
                        task.id, 
                        NodeStatus.DONE, 
                        result={
                            "message": strip_reasoning_markers(response_text),
                            "query_hash_rl": rl_meta.get("query_hash_rl"),
                            "arm_index": rl_meta.get("arm_index")
                        }
                    )
                    return
                
                action_type, action_payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")
                
                if action_type in ["complete", "done", "respond", "finish"]:
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    duration = time.time() - start_time
                    logger.info(f"Task completed. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(
                        task.id, 
                        NodeStatus.DONE, 
                        result={
                            "message": final_res,
                            "query_hash_rl": rl_meta.get("query_hash_rl"),
                            "arm_index": rl_meta.get("arm_index"),
                            "depth": rl_meta.get("depth")
                        }
                    )
                    return

                obs = ""
                if action_type == "hybrid_search":
                    try:
                        p = json.loads(action_payload) if isinstance(action_payload, str) else action_payload
                        # CognitiveRetriever handles depth, session context, and augmented query internally
                        chunks_text, retrieved_skills = await self.retriever.retrieve_context_with_meta(
                            query=p.get("query", query_goal),
                            session_id=session_id,
                            intent=task.payload.get("intent")
                        )
                        
                        # Push retrieval metadata back to session so future turns know which skills were consulted
                        await self.bus.push_session_turn(session_id, {
                            "user_msg": p.get("query", query_goal)[:200],
                            "skills_used": retrieved_skills,
                            "intent": task.payload.get("intent", ""),
                            "turn_type": "retrieval",
                        })

                        if not chunks_text or chunks_text.strip() == "":
                            obs = "Observation: No relevant context found."
                        else:
                            obs = f"Observation: Found relevant context:\n{chunks_text}"
                        
                        # Update RL metadata with local depth info (duck-typing for telemetry)
                        depth_meta = self.retriever.get_depth(task.payload.get("intent"))
                        rl_meta.update({
                            "top_k": depth_meta["top_k"],
                            "depth": depth_meta["depth"],
                            "query_hash_rl": depth_meta["query_hash_rl"]
                        })
                    except Exception as e:
                        obs = f"Observation: Search error: {e}"
                elif action_type == "web_fetch":
                    if not PLAYWRIGHT_AVAILABLE:
                        obs = "Observation: web_fetch unavailable."
                    else:
                        obs = "Observation: [Simulated web_fetch content]"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            duration = time.time() - start_time
            logger.warning(f"Max turns reached. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, 
                NodeStatus.FAILED, 
                result={"error_type": "max_turns", "error": "Max reasoning turns reached without finding an answer."}
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Critical error in execution loop: {e}. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, 
                NodeStatus.FAILED, 
                result={"error_type": "critical_failure", "error": str(e), "traceback": traceback.format_exc()}
            )

    async def run_forever(self):
        self._running = True
        logger.info(f"ResearchAgentWorker started (listening on A2A bus topic: {AgentRole.RAG.value})")
        
        async for msg in self.bus.listen(AgentRole.RAG.value):
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
