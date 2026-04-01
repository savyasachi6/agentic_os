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
import re as _re

from agent_core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.agent_types import NodeType, AgentRole, AgentResult, NodeStatus
from agent_core.llm.models import ModelTier
from agent_core.utils.logging_utils import log_event
from agent_core.utils.thought_utils import normalize_thought, should_publish
# RAG logic
from agent_core.rag.cognitive_retriever import CognitiveRetriever
from core.message_bus import A2ABus
from db.connection import init_db_pool

# Sandbox tools re-enabled (Phase 72)
import httpx
from bs4 import BeautifulSoup


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

    def _clean_model_url(self, raw: str) -> str:
        """Phase 101: Clean up model-generated URLs like url="https://..." """
        s = (raw or "").strip()
        if s.lower().startswith("url="):
            s = s[4:].strip()
        # Strip symmetric quotes
        if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
            s = s[1:-1].strip()
        return s

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action, parse_thought
        import time
        start_time = time.time()
        
        # 1. Initialize Contextual IDs and Goals
        query_goal = task.payload.get("query") or task.payload.get("goal") or task.content or "Unknown Goal"
        session_id = str(task.chain_id)
        
        # 2. Dynamic Date Injection (Phase 94)
        current_date_str = datetime.now().strftime("%B %d, %Y")
        system_prompt = self.system_prompt.replace("{{TODAY}}", current_date_str)
        # Handle legacy {current_date} placeholder if present
        system_prompt = system_prompt.replace("{current_date}", current_date_str)
        
        if "Today is" not in system_prompt:
            system_prompt = f"Today is {current_date_str}.\n\n" + system_prompt

        # 3. Build Message History
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"}
        ]

        logger.info(f"Task received: node_id={task.id}, role={AgentRole.RAG.value}, goal='{query_goal[:50]}...'")
        
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

                log_event(logger, "info", "research_turn_start", 
                          node_id=task.id, session_id=session_id, turn=i+1, max_turns=max_iterations)
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
                            summary_text = await self.llm.generate_async(summary_prompt, session_id=session_id, tier=ModelTier.FAST)
                            # 2. Embed and Store
                            emb, _ = await self.retriever.embedder.generate_embedding_async(summary_text)
                            await loop.run_in_executor(None, store_session_summary, session_id, summary_text, emb, 0, num_thoughts)
                            logger.info(f"Compaction complete for session {session_id} at turn {num_thoughts}.")
                        else:
                            logger.debug(f"Session {session_id} has {num_thoughts} thoughts, but only {num_thoughts - last_compacted_turn} since last compaction. Skipping.")
                except Exception as ce:
                    logger.error(f"Failed to compact session history: {ce}")

                # Phase 90: Explicit initialization to prevent UnboundLocalError
                thought_text: str = ""
                response_text: str = ""
                
                # Explicit Last Turn Nudge (Phase 87 Alignment)
                if i == max_iterations - 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have ONE turn remaining. After receiving the next "
                            "Observation, you MUST call "
                            'respond_direct(message=""" ... """) '
                            "with your complete final answer. Do not call any more tools."
                        )
                    })

                try:
                    response_text = await self.llm.generate_async(messages, session_id=session_id)
                except Exception as exc:
                    log_event(logger, "error", "llm_generation_failed", 
                              node_id=task.id, session_id=session_id, error=str(exc))
                    response_text = ""

                # Extract native model thinking tokens if present
                thinking_match = _re.search(r"<\|thinking\|>(.*?)(?:<\|/thinking\|>|$)", response_text, _re.DOTALL)
                if thinking_match:
                    thought_text = thinking_match.group(1).strip()
                    response_text = _re.sub(r"<\|thinking\|>.*?(?:<\|/thinking\|>|$)", "", response_text, flags=_re.DOTALL).strip()
                else:
                    from agent_core.reasoning import parse_thought
                    thought_text = parse_thought(response_text) if response_text else ""
                
                # Cleanup and Publish using Shared Utilities
                if not hasattr(self, "_last_published_thought"):
                    self._last_published_thought = ""

                if thought_text:
                    clean_thought = normalize_thought(thought_text)
                    if should_publish(clean_thought, self._last_published_thought):
                        await self.bus.publish(self.role.value, {
                            "type": "thought",
                            "content": clean_thought,
                            "session_id": session_id
                        })
                        self._last_published_thought = clean_thought
                    else:
                        log_event(logger, "debug", "thought_skipped_duplicate", 
                                  node_id=task.id, turn=i+1)

                # Fixing [Continuing research...] placeholder becoming a result
                if not response_text or response_text.strip() == "":
                    if i < max_iterations - 1:
                        logger.warning(
                            f"LLM returned empty response on turn {i+1}. "
                            f"Skipping turn. node_id={task.id}"
                        )
                        continue   # Skip turn — do NOT append garbage to messages
                    else:
                        await self.tree_store.update_node_status_async(
                            task.id,
                            NodeStatus.DONE,
                            result={"message": "I was unable to generate a response for this query. Please try again."}
                        )
                        return


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
                
                # Phase 103: Support clarifying nudge if model fails to 'act'
                action_data = parse_react_action(response_text)
                if not action_data and i < max_iterations - 1:
                    logger.warning(f"No action parsed on turn {i+1}. Injecting ReAct format nudge. node_id={task.id}")
                    messages.append({
                        "role": "user", 
                        "content": "Observation: I didn't see an 'Action:' line in your last response. Remember to follow the Thought/Action format exactly for every turn."
                    })
                    continue

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
                log_event(logger, "info", "research_action_parsed", 
                          node_id=task.id, session_id=session_id, turn=i+1, action_type=action_type)
                
                if action_type in ["complete", "done", "respond", "finish", "respond_direct"]:
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    duration_ms = int((time.time() - start_time) * 1000)
                    log_event(logger, "info", "research_task_done", 
                              node_id=task.id, session_id=session_id, duration_ms=duration_ms)
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

                # Phase 90: Explicit initialization to prevent UnboundLocalError
                p: dict = {}
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
                            # CognitiveRetriever now returns (context, skills, strategy) in Phase 5
                            chunks_text, retrieved_skills, strategy = await self.retriever.retrieve_context(
                                query=p.get("query", query_goal),
                                session_id=session_id,
                                intent=task.payload.get("intent")
                            )
                        except Exception as hse:
                            logger.warning(f"Hybrid search failed (likely DB restart): {hse}. Retrying in 2s...")
                            await asyncio.sleep(2.0)
                            chunks_text, retrieved_skills, strategy = await self.retriever.retrieve_context(
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
                        
                        # Update RL metadata with dynamic strategy info (Phase 5)
                        rl_meta.update({
                            "top_k": strategy.get("k", 10),
                            "depth": strategy.get("depth", 1), # strategy now contains k/hybrid/etc.
                            "arm_index": strategy.get("name", "unknown")
                        })
                        
                        messages.append({"role": "system", "content": obs})
                        continue
                    except Exception as e:
                        obs = f"Observation: Search error: {e}"
                elif action_type == "web_search":
                    query = p.get("query")
                    if not query:
                        obs = "Observation: Error: No query provided for web_search."
                    else:
                        try:
                            log_event(logger, "info", "browser_search_start", 
                                      node_id=task.id, session_id=session_id, query=query)
                            # Phase 103: Use the First-Class WebSearchAction tool
                            from agent_core.tools.tools import WebSearchAction
                            tool = WebSearchAction(query=query, max_results=5)
                            obs = await tool.run_async()
                        except Exception as e:
                            obs = f"Observation: web_search error: {e}"
                elif action_type == "web_fetch":
                    url = self._clean_model_url(p.get("url"))
                    if not url:
                        obs = "Observation: Error: No URL provided for web_fetch."
                    elif not url.startswith(("http://", "https://")):
                        obs = f"Observation: Error: Invalid URL protocol in '{url}'."
                    else:
                        try:
                            log_event(logger, "info", "web_fetch_start", 
                                      node_id=task.id, session_id=session_id, url=url)
                            # Phase 105: Use httpx for lightweight headless fetching
                            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                                resp = await client.get(url, headers={"User-Agent": "AgentOS/1.0"})
                                resp.raise_for_status()
                                
                                html = resp.text
                                soup = BeautifulSoup(html, "html.parser")
                                
                                # Remove script and style elements
                                for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
                                    script_or_style.decompose()
                                    
                                # Get clean text
                                text = soup.get_text(separator="\n")
                                lines = (line.strip() for line in text.splitlines())
                                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                                clean_text = "\n".join(chunk for chunk in chunks if chunk)
                                
                                title = soup.title.string.strip() if soup.title else "No Title Found"
                                if len(clean_text) > 10_000:
                                    clean_text = clean_text[:10_000] + "\n... [truncated]"
                                    
                                obs = f"Observation: Success [URL: {url}]\nTitle: {title}\nContent: {clean_text}"
                        except Exception as e:
                            obs = f"Observation: web_fetch error: {e}"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            duration_ms = int((time.time() - start_time) * 1000)
            log_event(logger, "warning", "max_turns", 
                      node_id=task.id, session_id=session_id, duration_ms=duration_ms)
            assert task.id is not None
            # Revert to DONE with partial success instead of FAILED (Alignment pass)
            last_resp = messages[-1]["content"] if messages[-1]["role"] == "assistant" else "Max research turns reached."
            await self.tree_store.update_node_status_async(
                task.id, 
                NodeStatus.DONE, 
                result={"message": last_resp, "status": "partial_success", "error": "Max iterations reached."}
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_event(logger, "error", "worker_error", 
                      node_id=task.id, session_id=session_id, 
                      error_type=type(e).__name__, duration_ms=duration_ms, exc_info=True)
            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, 
                NodeStatus.FAILED, 
                result={"error_type": "critical_failure", "error": str(e), "traceback": traceback.format_exc()}
            )

    async def run_forever(self):
        self._running = True
        logger.info(f"ResearchAgentWorker started (listening on A2A bus topic: {AgentRole.RAG.value})")
        
        while self._running:
            try:
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
            except Exception as e:
                logger.warning(f"ResearchAgentWorker listener dropped: {e}. Retrying in 5s...")
                await asyncio.sleep(5)
