"""
agents/executor.py
==================
Refactored UniversalAgentWorker (now ExecutorAgentWorker) using modular imports.
Handles general shell execution and catch-all specialist tasks.
Depends on db.queries.commands, db.models, core.types, llm.client, and core.guards.
"""
import asyncio
import logging
import json
import subprocess
import os
from typing import Optional, Dict, Any

from llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.types import Intent, AgentRole, NodeStatus
from agent_core.guards import is_safe_command
from agents.a2a_bus import A2ABus

logger = logging.getLogger("agentos.agents.executor")

class ExecutorAgentWorker:
    """
    Background worker for generic specialist tasks (AgentRole.SPECIALIST).
    Can execute shell commands and synthesized responses.
    """
    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        self.bus = A2ABus()
        self.system_prompt = "You are the ExecutorAgent. Use shell_execute for CLI tasks or respond() to finish."
        self._running = False
        self._load_prompt()

    def _load_prompt(self):
        # Optional: Load from llm/prompts/executor_agent_prompt.md if it exists
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "llm", "prompts", "executor_agent_prompt.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action # Temporarily
        
        query = task.payload.get("query", task.content or "No content")
        print(f"[ExecutorAgent] Received Task {task.id}: {query[:50]}")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {query}"}
        ]

        max_iterations = task.payload.get("max_turns", 5)
        for i in range(max_iterations):
            try:
                response = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response})
                
                action_data = parse_react_action(response)
                if not action_data:
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": response})
                    return

                action_type, action_payload = action_data
                
                if action_type in ["respond", "done", "complete", "finish"]:
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": action_payload})
                    return
                
                if action_type == "shell_execute":
                    if not is_safe_command(action_payload):
                        obs = f"Observation Error: Command '{action_payload}' is blocked for safety."
                    else:
                        loop = asyncio.get_running_loop()
                        # Use a 30s timeout and capture output
                        try:
                            res = await loop.run_in_executor(
                                None, 
                                lambda: subprocess.run(action_payload, shell=True, capture_output=True, text=True, timeout=30)
                            )
                            obs = f"Observation: {res.stdout}\n{res.stderr}"
                        except subprocess.TimeoutExpired:
                            obs = "Observation Error: Command timed out."
                        except Exception as e:
                            obs = f"Observation Error: {e}"
                    messages.append({"role": "user", "content": obs})
                else:
                    messages.append({"role": "user", "content": f"Observation: Unknown action {action_type}"})

            except Exception as e:
                logger.error("ExecutorAgent loop error: %s", e)
                assert task.id is not None
                await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})
                return
        
        assert task.id is not None
        await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": "Max iterations reached"})

    async def run_forever(self):
        self._running = True
        print("[ExecutorAgent] Worker started (listening on A2A bus).")
        
        async for msg in self.bus.listen(AgentRole.SPECIALIST.value):
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
