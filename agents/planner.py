"""
agents/planner.py
=================
Refactored PlannerAgentWorker using modular imports.
Responsible for task decomposition and planning.
Depends on db.queries.commands, db.models, core.types, and llm.client.
"""
import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List

from llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from core.types import AgentRole, NodeStatus

logger = logging.getLogger("agentos.agents.planner")

class PlannerAgentWorker:
    """
    Background worker that handles task decomposition.
    Transforms complex goals into a series of executable nodes.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.system_prompt = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Modular architecture path: llm/prompts/planner_agent_prompt.md (or similar)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "llm", "prompts", "planner_agent_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the PlannerAgent. Decompose goals into task nodes."

    async def _process_task(self, task: Node):
        goal = task.payload.get("goal", task.content or "No goal")
        print(f"[PlannerAgent] Received Goal: {goal}")
        
        # In a real implementation, the LLM would output a schema of nodes.
        # For the refactor skeleton, we implement a basic static plan or small LLM logic.
        
        # 1. Build decomposition prompt
        user_content = f"Goal: {goal}\n\nDecompose this into 2-3 specific steps. Return JSON list of tasks."
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        try:
            # We'll use get_llm().generate_async or similar
            response = await self.llm.generate_async(messages)
            # (Parse response and create nodes... simplified for now)
            
            # For demonstration, we'll just mark it DONE with a dummy plan.
            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, NodeStatus.DONE, 
                result={"plan": "Decomposed into steps...", "raw": response}
            )
        except Exception as e:
            logger.error("PlannerAgent error: %s", e)
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        print("[PlannerAgent] Worker started.")
        while self._running:
            try:
                # Polling for PLANNER role tasks
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.PLANNER)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("Polling error: %s", e)
                await asyncio.sleep(poll_interval)
