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
            rl_action = await self.rl_client.get_retrieval_action(query_goal, session_id)
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
                            await self.bus.publish(
                                self.role.value,
                                {"type": "thought", "content": content, "session_id": session_id},
                            )
                        elif chunk_type == "token":
                            response_text += content
                            await self.bus.publish(
                                self.role.value,
                                {"type": "token", "content": content, "session_id": session_id},
                            )
                        elif chunk_type == "error":
                            logger.error(f"Streaming error on turn {i+1}: {content}")
                            break

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
                            obs = f"Observation:\n{context_block}"
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
                                else f"Observation:\n{out}"
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
                            obs = f"Observation:\n{res.data['output']}"
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
