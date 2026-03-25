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
from agent_core.graph.state import AgentState
from agent_core.agent_types import NodeType, AgentRole, AgentResult
# RAG logic
from rag.retriever import HybridRetriever
from agents.a2a_bus import A2ABus

# Sandbox tools temporarily disabled until moved to core/sandbox
PLAYWRIGHT_AVAILABLE = False
handle_browser_navigate = None
ToolCallRequest = None

logger = logging.getLogger("agentos.agents.rag")

class ResearchAgent:
    """
    Background worker that polls for `AgentRole.RAG` nodes.
    Performs information retrieval and synthesis.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.retriever = HybridRetriever()
        self.bus = A2ABus()
        self.system_prompt = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Adjusted for modular architecture: llm/prompts/research_agent_prompt.md
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "prompts", "rag.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the RAGAgent. Perform research and retrieval."

    async def _process_task(self, task: Node):
        query_goal = task.payload.get("query", "Unknown Goal")
        session_id = str(task.chain_id)
        print(f"[RAGAgent] Received Task {task.id}: {query_goal}")
        

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
                from agent_core.reasoning import parse_react_action
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

                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": final_res})
                    return

                obs = ""
                if action_type == "hybrid_search":
                    try:
                        p = json.loads(action_payload) if isinstance(action_payload, str) else action_payload
                        chunks_text = await self.retriever.retrieve_context_async(query=p.get("query", query_goal), session_id=session_id)
                        obs = f"Observation: Found relevant context:\n{chunks_text}"
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

    async def run_forever(self):
        self._running = True
        print("[RAGAgent] Worker started (listening on A2A bus).")
        
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
                logger.error("Error processing A2A message: %s", e)
