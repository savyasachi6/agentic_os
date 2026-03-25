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
from agent_core.agent_types import Intent, AgentRole, NodeStatus
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
        prompt_path = os.path.join(root_dir, "prompts", "executor.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action # Temporarily
        from datetime import datetime
        
        query = task.payload.get("query", task.content or "No content")
        print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Received Task {task.id}: {query[:50]}")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {query}"}
        ]

        max_iterations = task.payload.get("max_turns", 5)
        for i in range(max_iterations):
            try:
                print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Turn {i+1}: Starting LLM generation...")
                response = await self.llm.generate_async(messages)
                print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Turn {i+1}: Received LLM response.")
                messages.append({"role": "assistant", "content": response})
                
                action_data = parse_react_action(response)
                if not action_data:
                    print(f"[{datetime.now().isoformat()}] [ExecutorAgent] No action parsed. Completing task.")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": response})
                    return

                action_type, action_payload = action_data
                
                if action_type in ["respond", "done", "complete", "finish"]:
                    print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Action: {action_type}. Updating DB...")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": action_payload})
                    return
                
                if action_type == "shell_execute":
                    print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Action: shell_execute. Payload: {action_payload}")
                    if not is_safe_command(action_payload):
                        obs = f"Observation Error: Command '{action_payload}' is blocked for safety."
                    else:
                        loop = asyncio.get_running_loop()
                        
                        # Prepare environment with Task ID for direct reporting
                        env = os.environ.copy()
                        env["AGENTOS_TASK_ID"] = str(task.id)
                        
                        # Use a 30s timeout and capture output
                        try:
                            # Use a helper to run subprocess with custom env
                            def run_sub():
                                return subprocess.run(
                                    action_payload, 
                                    shell=True, 
                                    capture_output=True, 
                                    text=True, 
                                    timeout=30,
                                    env=env
                                )
                            
                            res = await loop.run_in_executor(None, run_sub)
                            obs = f"Observation: {res.stdout}\n{res.stderr}"
                            if res.returncode != 0:
                                obs = f"Observation Error (code {res.returncode}): {res.stderr}\n{res.stdout}"
                        except subprocess.TimeoutExpired:
                            obs = "Observation Error: Command timed out after 30 seconds."
                        except Exception as e:
                            obs = f"Observation Error: {e}"
                    messages.append({"role": "user", "content": obs})
                    print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Turn {i+1}: Action completed. Observation captured.")
                else:
                    messages.append({"role": "user", "content": f"Observation: Unknown action {action_type}"})

            except Exception as e:
                logger.error("ExecutorAgent loop error: %s", e)
                assert task.id is not None
                await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})
                return
        
        print(f"[{datetime.now().isoformat()}] [ExecutorAgent] Max iterations ({max_iterations}) reached.")
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
