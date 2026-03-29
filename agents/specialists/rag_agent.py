# agents/rag_agent.py
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional

from core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from core.agent_types import AgentRole, NodeStatus
from rag.retriever import HybridRetriever
from core.tool_registry import registry
from core.llm.routing import RLRoutingClient
from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.rag")


class ResearchAgentWorker(AgentWorker):
    def __init__(self, store: TreeStore = None, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.retriever = HybridRetriever()
        self.rl_client = RLRoutingClient()
        self.role = AgentRole.RAG
        self.system_prompt = ""
        self._load_prompt()
        super().__init__(role=self.role, agent=self, store=store or TreeStore())

    def _load_prompt(self):
        from prompts.loader import load_prompt
        try:
            self.system_prompt = load_prompt("rag")
        except Exception as e:
            logger.error(f"Failed to load RAG prompt: {e}")
            self.system_prompt = "You are the RAGAgent. Perform research and retrieval."

    async def _process_task(self, task: Node):
        from core.reasoning import parse_react_action, strip_all_reasoning

        import time
        start_time = time.time()

        query_goal = task.payload.get("query") or task.payload.get("goal") or "Unknown Goal"
        session_id = str(task.chain_id)

        logger.info(
            f"Task received: node_id={task.id}, role={AgentRole.RAG.value}, goal='{query_goal[:80]}'"
        )

        current_date = datetime.now().strftime("%B %d, %Y")
        system_content = self.system_prompt.replace("{current_date}", current_date)
        if "Today is" not in system_content:
            system_content = f"Today is {current_date}.\n\n{system_content}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Task Goal: {query_goal}\n\nPayload: {json.dumps(task.payload)}"},
        ]

        try:
            # Phase 3: Use real embeddings for RL routing decision (Hardened with Retry)
            query_vec = [0.0] * 1024
            for attempt in range(3):
                try:
                    # Timeout wrapped to prevent blocking the entire agent loop
                    query_vec, _ = await asyncio.wait_for(
                        self.retriever.embedder.generate_embedding_async(query_goal),
                        timeout=5.0
                    )
                    break
                except asyncio.TimeoutError:
                    logger.warning(f"Embedding timeout attempt {attempt+1}/3")
                except Exception as e:
                    logger.warning(f"Embedding failed attempt {attempt+1}/3: {e}")
                    break

            rl_action = await self.rl_client.get_retrieval_action(
                query_goal, 
                session_id,
                query_embedding=query_vec
            )
            current_top_k = rl_action["top_k"]
            rl_meta = {
                "query_hash_rl": rl_action.get("query_hash_rl"),
                "arm_index": rl_action.get("action"),
                "depth": rl_action.get("depth"),
                "top_k": current_top_k,
                "speculative": rl_action.get("speculative", False),
            }

            await self.bus.publish(
                self.role.value,
                {
                    "type": "rl_metadata",
                    "content": json.dumps(rl_meta),
                    "session_id": session_id,
                },
            )

            max_iterations = task.payload.get("max_turns", 6)

            for i in range(max_iterations):
                current_node = await self.tree_store.get_node_by_id_async(task.id)
                if not current_node or current_node.status not in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    logger.warning(f"Task {task.id} abandoned by coordinator.")
                    return

                status_msg = f"Reasoning Turn {i + 1}/{max_iterations}..."
                await self.tree_store.update_node_status_async(
                    task.id,
                    NodeStatus.PENDING,
                    result={"progress": status_msg},
                )

                response_text = ""
                current_turn_thoughts = ""
                max_llm_retries = 3

                for retry_idx in range(max_llm_retries):
                    async for chunk in self.llm.generate_streaming(messages, session_id=session_id):
                        chunk_type = chunk.get("type")
                        content = chunk.get("content", "")

                        if chunk_type == "thought":
                            current_turn_thoughts += content
                            # Phase 15: Suppress raw thoughts to prevent UI leakage
                        elif chunk_type == "token":
                            response_text += content
                            # Phase 15: Suppress raw tokens to keep UI clean
                        elif chunk_type == "error":
                            logger.error(f"Streaming error on turn {i+1}: {content}")
                            break

                    # Provide a quick status update to show progress without raw tokens
                    await self.bus.publish(
                        self.role.value,
                        {"type": "status", "content": f"Thinking (Turn {i+1})...", "session_id": session_id},
                    )

                    if response_text.strip() or current_turn_thoughts.strip():
                        break

                    if retry_idx < max_llm_retries - 1:
                        wait_sec = 2 * (retry_idx + 1)
                        await self.bus.publish(
                            self.role.value,
                            {
                                "type": "warning",
                                "content": (
                                    f"Inference stall detected. Retrying in {wait_sec}s "
                                    f"(attempt {retry_idx+1}/{max_llm_retries})"
                                ),
                                "session_id": session_id,
                            },
                        )
                        await asyncio.sleep(wait_sec)

                full_raw_text = current_turn_thoughts + response_text

                if not full_raw_text.strip():
                    await self.tree_store.update_node_status_async(
                        task.id,
                        NodeStatus.FAILED,
                        result={"error": "The AI model returned no content after multiple attempts."},
                    )
                    return

                messages.append({"role": "assistant", "content": full_raw_text})
                action_data = parse_react_action(full_raw_text)

                if not action_data:
                    final_message = strip_all_reasoning(full_raw_text)
                    # Phase 15: Heuristic reward and corrected arm_index
                    if rl_meta.get("query_hash_rl"):
                        reward = self._compute_reward(final_message, i + 1, max_iterations)
                        await self.rl_client.submit_feedback(
                            query_hash=rl_meta["query_hash_rl"],
                            reward=reward,
                            arm_index=rl_meta.get("arm_index", 2),
                            depth=i + 1,
                            speculative=bool(rl_meta.get("speculative")),
                            latency_ms=(time.time() - start_time) * 1000,
                            success=True,
                            hallucination_flag=self._detect_hallucination(final_message),
                        )

                    await self.tree_store.update_node_status_async(
                        task.id,
                        NodeStatus.DONE,
                        result={
                            "message": final_message,
                            **rl_meta,
                        },
                    )
                    return

                action_type, action_payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")

                if action_type in ("complete", "done", "respond", "finish"):
                    final_res = action_payload
                    if isinstance(final_res, str):
                        final_res = self._cleanup_final_payload(final_res)

                    # Phase 15: Heuristic reward and corrected arm_index
                    if rl_meta.get("query_hash_rl"):
                        reward = self._compute_reward(final_res, i + 1, max_iterations)
                        await self.rl_client.submit_feedback(
                            query_hash=rl_meta["query_hash_rl"],
                            reward=reward,
                            arm_index=rl_meta.get("arm_index", 2),
                            depth=i + 1,
                            speculative=bool(rl_meta.get("speculative")),
                            latency_ms=(time.time() - start_time) * 1000,
                            success=True,
                            hallucination_flag=self._detect_hallucination(final_res),
                        )

                    await self.tree_store.update_node_status_async(
                        task.id,
                        NodeStatus.DONE,
                        result={
                            "message": final_res,
                            **rl_meta,
                        },
                    )
                    return

                if action_type == "hybrid_search":
                    query = str(action_payload).strip()
                    try:
                        context_block = await self.retriever.retrieve_context_async(
                            query,
                            top_k=current_top_k,
                            session_id=session_id,
                        )
                        if context_block:
                            obs = f"Observation (retrieved context — synthesize this into a direct answer, do NOT bullet-point the chunks):\n{context_block}"
                        else:
                            # Dynamic Phase: Provide a hint to the AI to be more conversational if no data is found
                            obs = (
                                "Observation: No relevant local information was found for this specific query. "
                                "HINT: Instead of a canned failure message, explain what you ARE capable of "
                                "searching for, or ask for a different topic in a friendly manner."
                            )
                    except Exception as e:
                        obs = f"Observation: Local search error: {e}"

                elif action_type == "web_search":
                    query = str(action_payload).strip()
                    try:
                        res = await registry.invoke("web_search", query=query, count=5)
                        if hasattr(res, "data") and "output" in res.data:
                            out = res.data["output"]
                            obs = (
                                f"Observation: Web search returned no results for '{query}'."
                                if "no results" in out.lower()
                                else f"Observation (retrieved context — synthesize this into a direct answer, do NOT bullet-point the chunks):\n{out}"
                            )
                        elif getattr(res, "success", True) is False:
                            obs = (
                                "Observation: Web search is unavailable. "
                                f"Reason: {getattr(res, 'error_trace', 'unknown')}"
                            )
                        else:
                            obs = f"Observation: {str(res)}"
                    except Exception as e:
                        obs = f"Observation: Web search error: {e}"

                elif action_type == "web_scrape":
                    url = str(action_payload).strip()
                    try:
                        res = await registry.invoke("web_scrape", url=url)
                        if hasattr(res, "data") and "output" in res.data:
                            obs = f"Observation (scraped page content — synthesize this into a direct answer, do NOT bullet-point the chunks):\n{res.data['output']}"
                        else:
                            obs = f"Observation: {str(res)}"
                    except Exception as e:
                        obs = f"Observation: Web scrape error: {e}"

                else:
                    obs = (
                        f"Observation: Unknown action '{action_type}'. "
                        "Use hybrid_search, web_search, web_scrape, or respond."
                    )

                await self.bus.publish(
                    self.role.value,
                    {
                        "type": "observation",
                        "content": obs,
                        "session_id": session_id,
                    },
                )
                messages.append({"role": "user", "content": obs})

            # Phase 15: Submit failure feedback with corrected arm_index
            if rl_meta.get("query_hash_rl"):
                await self.rl_client.submit_feedback(
                    query_hash=rl_meta["query_hash_rl"],
                    reward=0.0,
                    arm_index=rl_meta.get("arm_index", 2),
                    depth=max_iterations,
                    speculative=bool(rl_meta.get("speculative")),
                    latency_ms=(time.time() - start_time) * 1000,
                    success=False,
                    hallucination_flag=True,  # Failure to find answer is treated as a logic gap
                )

            await self.tree_store.update_node_status_async(
                task.id,
                NodeStatus.FAILED,
                result={
                    "error_type": "max_turns",
                    "error": "Max reasoning turns reached without finding an answer.",
                    **rl_meta,
                },
            )

        except Exception as e:
            logger.exception(f"Critical error in execution loop: {e}")
            await self.tree_store.update_node_status_async(
                task.id,
                NodeStatus.FAILED,
                result={
                    "error_type": "critical_failure",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    def _compute_reward(self, answer: str, depth: int, max_depth: int) -> float:
        """
        Phase 15: Simple heuristic reward
        - 0.0 if the answer is a known fallback/failure string
        - Linearly decays with depth to reward shallower successful retrievals
        """
        if not answer:
            return 0.0
        fallback_phrases = [
            "i couldn't find", "no relevant", "no results",
            "i don't know", "i am unable", "cannot find",
            "not clear", "needs more context"
        ]
        ans_lower = answer.lower()
        if any(p in ans_lower for p in fallback_phrases):
            return 0.2  # partial credit — it ran, but result was weak
        
        # Reward decays linearly: depth=1 -> 1.0, depth=max_depth -> 0.5
        return max(0.5, 1.0 - 0.5 * (depth / max_depth))

    def _detect_hallucination(self, answer: str) -> bool:
        """Heuristic: answer contains speculative markers without grounding."""
        speculative_markers = [
            "i think", "i believe", "probably", "might be", "could be",
            "i'm not sure", "i'm not certain", "as far as i know"
        ]
        ans_lower = answer.lower()
        has_speculation = any(m in ans_lower for m in speculative_markers)
        has_grounding = any(m in ans_lower for m in ["according to", "the document", "retrieved", "found in"])
        return has_speculation and not has_grounding

    @staticmethod
    def _cleanup_final_payload(payload: str) -> str:
        text = payload.strip()

        prefixes = [
            "summary=",
            "message=",
            "content=",
            "payload=",
            "goal=",
            "task=",
            "query=",
            "command=",
            "answer=",
            "result=",
            "response=",
        ]
        for prefix in prefixes:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if len(text) >= 2 and (
            (text[0] == '"' and text[-1] == '"') or
            (text[0] == "'" and text[-1] == "'")
        ):
            text = text[1:-1].strip()

        return text


    # run_forever removed in Phase 5: Now managed by AgentWorker backbone.
