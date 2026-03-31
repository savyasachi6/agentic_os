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
from agent_core.llm.models import ModelTier
# RAG logic
from agent_core.rag.cognitive_retriever import CognitiveRetriever
from core.message_bus import A2ABus
from db.connection import init_db_pool

# Sandbox tools re-enabled (Phase 72)
from sandbox.browser_tools import handle_browser_navigate, ToolCallRequest, PLAYWRIGHT_AVAILABLE

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
        self.compaction_threshold = 50
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
                loop = asyncio.get_running_loop()

                # Log original user goal as a 'user' thought for memory retrieval
                try:
                    query_goal = task.payload.get("goal", task.payload.get("query", ""))
                    if query_goal:
                        _uq_emb, _ = await self.retriever.embedder.generate_embedding_async(query_goal[:500])
                        from db.queries.thoughts import log_thought
                        from db.connection import get_db_connection
                        
                        # Resilience wrap: detect if DB is down and wait/retry once
                        try:
                            await loop.run_in_executor(None, log_thought, session_id, "user", query_goal[:500], _uq_emb)
                        except Exception as dbe:
                            logger.warning(f"Initial thought log failed (likely DB restart): {dbe}. Retrying in 2s...")
                            await asyncio.sleep(2.0)
                            await loop.run_in_executor(None, log_thought, session_id, "user", query_goal[:500], _uq_emb)
                except Exception as e:
                    logger.error(f"Failed to log user query thought: {e}")

                # Check for session history compaction (Gap 5 Closure)
                try:
                    from db.queries.thoughts import get_session_history, store_session_summary, get_last_compacted_turn
                    # Resilience wrap for history retrieval
                    try:
                        history = await loop.run_in_executor(None, get_session_history, session_id)
                    except Exception:
                        await asyncio.sleep(1.0)
                        history = await loop.run_in_executor(None, get_session_history, session_id)
                        
                    num_thoughts = len(history)
                    if num_thoughts >= self.compaction_threshold:
                        last_compacted_turn = await loop.run_in_executor(None, get_last_compacted_turn, session_id)
                        if (num_thoughts - last_compacted_turn) >= 20:
                            logger.info(f"Session {session_id} exceeds threshold ({num_thoughts}) and delta guard. Compacting...")
                            # 1. Summarize
                            summary_prompt = [
                                {"role": "system", "content": "Summarize the key findings and progress of this research session so far. Focus on what was found and what is still needed."},
                                {"role": "user", "content": str(history)}
                            ]
                            summary_text = await self.llm.generate_async(summary_prompt, tier=ModelTier.FAST)
                            # 2. Embed and Store
                            emb, _ = await self.retriever.embedder.generate_embedding_async(summary_text)
                            await loop.run_in_executor(None, store_session_summary, session_id, summary_text, emb, 0, num_thoughts)
                            logger.info(f"Compaction complete for session {session_id} at turn {num_thoughts}.")
                        else:
                            logger.debug(f"Session {session_id} has {num_thoughts} thoughts, but only {num_thoughts - last_compacted_turn} since last compaction. Skipping.")
                except Exception as ce:
                    logger.error(f"Failed to compact session history: {ce}")

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
                
                from agent_core.reasoning import clean_thought_text
                
                # Deduplication logic (Phase 87 Alignment)
                if not hasattr(self, "_last_published_thought"):
                    self._last_published_thought = ""

                if thought_text:
                    # Comprehensive cleanup of internal markers (Phase 87)
                    clean_thought = clean_thought_text(thought_text)
                    
                    if clean_thought and clean_thought != self._last_published_thought:
                        turn_label = f"**[Turn {i+1}/{max_iterations}]**\n\n"
                        await self.bus.publish(self.role.value, {
                            "type": "thought",
                            "content": turn_label + clean_thought,
                            "session_id": session_id
                        })
                        self._last_published_thought = clean_thought
                    else:
                        logger.debug("Skipping redundant thought publishing", extra={"turn": i+1, "node_id": task.id})

                # Explicit Last Turn Nudge (Phase 87 Alignment)
                if i == max_iterations - 1:
                     messages.append({
                         "role": "user", 
                         "content": "CRITICAL: This is your LAST TURN. Based on the tools called so far, provide a final BEST-EFFORT response to the query. Do not call any more tools."
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
                
                # Fix Break 4: Persist thought for future memory retrieval
                try:
                    from db.queries.thoughts import log_thought
                    # Reuse already-instantiated embedder from self.retriever
                    loop = asyncio.get_running_loop()
                    _emb_val, _ = await self.retriever.embedder.generate_embedding_async(response_text[:500])
                    await loop.run_in_executor(None, log_thought, session_id, "assistant", response_text[:500], _emb_val)
                except Exception as e:
                    logger.error(f"Failed to log assistant thought: {e}")
                
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

                # Unified payload parsing to prevent UnboundLocalError (Gap 78 Stabilization)
                p = {}
                if isinstance(action_payload, str):
                    try:
                        p = json.loads(action_payload) if action_payload.strip().startswith("{") else {"query": action_payload, "url": action_payload}
                    except Exception:
                        p = {"query": action_payload, "url": action_payload}
                elif isinstance(action_payload, dict):
                    p = action_payload

                obs = ""
                if action_type == "hybrid_search":
                    try:
                        # CognitiveRetriever handles depth, session context, and augmented query internally
                        
                        # Resilience wrap for DB/VectorStore access
                        try:
                            chunks_text, retrieved_skills = await self.retriever.retrieve_context_with_meta(
                                query=p.get("query", query_goal),
                                session_id=session_id,
                                intent=task.payload.get("intent")
                            )
                        except Exception as hse:
                            logger.warning(f"Hybrid search failed (likely DB restart): {hse}. Retrying in 2s...")
                            await asyncio.sleep(2.0)
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
                            obs = f"[CONTEXT_GROUNDING]\nThe following information was retrieved from the brain for this task:\n\n{chunks_text}"
                        
                        # Update RL metadata with local depth info (duck-typing for telemetry)
                        depth_meta = self.retriever.get_depth(task.payload.get("intent"))
                        rl_meta.update({
                            "top_k": depth_meta["top_k"],
                            "depth": depth_meta["depth"],
                        })
                        
                        messages.append({"role": "system", "content": obs})
                        continue
                    except Exception as e:
                        obs = f"Observation: Search error: {e}"
                elif action_type == "web_search":
                    if not PLAYWRIGHT_AVAILABLE:
                        obs = "Observation: web_search unavailable."
                    else:
                        query = p.get("query")
                        if not query:
                            obs = "Observation: Error: No query provided for web_search."
                        else:
                            try:
                                # Map search to a Google Search navigation call
                                search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                                req = ToolCallRequest(path=search_url, args={})
                                response = handle_browser_navigate(req)
                                if response.success:
                                    res = response.result
                                    obs = f"Observation: Success [Search: {query}]\nResults: {res['content']}"
                                else:
                                    obs = f"Observation: web_search failed: {response.error}"
                            except Exception as e:
                                obs = f"Observation: web_search error: {e}"
                elif action_type == "web_fetch":
                    if not PLAYWRIGHT_AVAILABLE:
                        obs = "Observation: web_fetch unavailable."
                    else:
                        url = p.get("url")
                        if not url:
                            obs = "Observation: Error: No URL provided for web_fetch."
                        else:
                            try:
                                # Use the production browser-navigate tool
                                req = ToolCallRequest(path=url, args={})
                                response = handle_browser_navigate(req)
                                if response.success:
                                    res = response.result
                                    obs = f"Observation: Success [URL: {res['url']}]\nTitle: {res['title']}\nContent: {res['content']}"
                                else:
                                    obs = f"Observation: web_fetch failed: {response.error}"
                            except Exception as e:
                                obs = f"Observation: web_fetch error: {e}"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            duration = int((time.time() - start_time) * 1000)
            logger.warning("Max turns reached", extra={
                "event": "max_turns",
                "role": self.role.value,
                "node_id": task.id,
                "session_id": session_id,
                "duration_ms": duration
            })
            assert task.id is not None
            # Revert to DONE with partial success instead of FAILED (Alignment pass)
            last_resp = messages[-1]["content"] if messages[-1]["role"] == "assistant" else "Max research turns reached."
            await self.tree_store.update_node_status_async(
                task.id, 
                NodeStatus.DONE, 
                result={"message": last_resp, "status": "partial_success", "error": "Max iterations reached."}
            )

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            logger.error("Critical error in research loop", extra={
                "event": "worker_error",
                "role": self.role.value,
                "node_id": task.id,
                "session_id": session_id,
                "error_type": type(e).__name__,
                "duration_ms": duration
            }, exc_info=True)
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
