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

from llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from core.types import AgentRole, NodeStatus
from agent_memory.cache import FractalCache # Temporarily
from agent_rag.retrieval.retriever import HybridRetriever # Temporarily

try:
    from agent_sandbox.browser_tools import handle_browser_navigate, PLAYWRIGHT_AVAILABLE
    from agent_sandbox.models import ToolCallRequest
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    handle_browser_navigate = None
    ToolCallRequest = None

logger = logging.getLogger("agentos.agents.rag")

class RAGAgentWorker:
    """
    Background worker that polls for `AgentRole.RAG` nodes.
    Performs information retrieval and synthesis.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.cache = FractalCache()
        self.retriever = HybridRetriever()
        self.system_prompt = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Adjusted for modular architecture: llm/prompts/research_agent_prompt.md
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "llm", "prompts", "research_agent_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the RAGAgent. Perform research and retrieval."

    async def _process_task(self, task: Node):
        query_goal = task.payload.get("query", "Unknown Goal")
        session_id = str(task.chain_id)
        print(f"[RAGAgent] Received Task {task.id}: {query_goal}")
        
        cached = await self.cache.get_cached_response_async(query_goal)
        if cached:
            print(f"[RAGAgent] Cache hit.")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result=cached["response"])
            return

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
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})
                
                # Using a local parse helper or importing from intent in future
                from agent_core.loop.thought_loop import parse_react_action
                action_data = parse_react_action(response_text)
                
                if not action_data:
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": response_text})
                    return
                
                action_type, action_payload = action_data
                
                if action_type in ["complete", "done", "respond", "finish"]:
                    try:
                        final_res = json.loads(action_payload) if isinstance(action_payload, str) and action_payload.strip().startswith("{") else action_payload
                    except Exception:
                        final_res = action_payload

                    asyncio.create_task(self.cache.set_cached_response_async(
                        query=query_goal, response={"message": final_res}, strategy_used="rag_worker"
                    ))
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": final_res})
                    return

                obs = ""
                if action_type == "hybrid_search":
                    try:
                        p = json.loads(action_payload) if isinstance(action_payload, str) else action_payload
                        chunks = await self.retriever.retrieve_async(query=p.get("query", query_goal), session_id=session_id)
                        obs = f"Observation: Found {len(chunks)} chunks: " + json.dumps([{"c": c.content[:100]} for c in chunks])
                    except Exception as e:
                        obs = f"Observation: Search error: {e}"
                elif action_type == "web_fetch":
                    if not PLAYWRIGHT_AVAILABLE:
                        obs = "Observation: web_fetch unavailable."
                    else:
                        # Logic simplified for the refactor skeleton
                        obs = "Observation: [Simulated web_fetch content]"
                else:
                    obs = f"Observation: Unknown action {action_type}"
                
                messages.append({"role": "user", "content": obs})
                
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Max turns reached"})

        except Exception as e:
            logger.exception("RAGAgent error: %s", e)
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        print("[RAGAgent] Worker started.")
        while self._running:
            try:
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.RAG)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("Polling error: %s", e)
                await asyncio.sleep(poll_interval)
