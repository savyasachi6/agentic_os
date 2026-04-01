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

from agent_core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.agent_types import Intent, AgentRole, NodeStatus
from agent_core.guards import is_safe_command
from agent_core.agents.core.a2a_bus import A2ABus

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
        from agent_core.prompts import load_prompt
        try:
            self.system_prompt = load_prompt("core", "executor")
        except Exception as e:
            logger.error(f"Failed to load executor prompt: {e}")
            self.system_prompt = "You are the ExecutorAgent. Use shell_execute for CLI tasks or respond() to finish."

    async def _process_task(self, task: Node):
        from agent_core.reasoning import parse_react_action
        import time
        from datetime import datetime
        
        start_time = time.time()
        query = task.payload.get("query", task.content or "No content")
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.SPECIALIST.value}, goal='{query[:50]}...'")
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {query}"}
        ]

        max_iterations = task.payload.get("max_turns", 5)
        try:
            for i in range(max_iterations):
                logger.info(f"Turn {i+1}/{max_iterations}: Starting LLM generation...")
                response = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response})
                
                action_data = parse_react_action(response)
                if not action_data:
                    # Phase 103: Recovery Nudge for Executor Agent
                    if i < max_iterations - 1:
                        logger.warning(f"No action parsed on turn {i+1}. Injecting ReAct format nudge. node_id={task.id}")
                        messages.append({
                            "role": "user", 
                            "content": "Observation: I didn't see an 'Action:' line in your last response. Remember to follow the Thought/Action format exactly for every turn."
                        })
                        continue

                    duration = time.time() - start_time
                    logger.info(f"No action parsed after retries. Completing task. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": response})
                    return

                action_type, action_payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")
                
                if action_type in ["respond", "done", "complete", "finish", "respond_direct", "complete_task"]:
                    duration = time.time() - start_time
                    logger.info(f"Action: {action_type}. Updating DB. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": action_payload})
                    return
                
                if action_type == "shell_execute":
                    if not is_safe_command(action_payload):
                        obs = f"Observation Error: Command '{action_payload}' is blocked for safety."
                    else:
                        loop = asyncio.get_running_loop()
                        env = os.environ.copy()
                        env["AGENTOS_TASK_ID"] = str(task.id)
                        
                        try:
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
                else:
                    messages.append({"role": "user", "content": f"Observation: Unknown action {action_type}"})

            duration = time.time() - start_time
            logger.warning(f"Max iterations ({max_iterations}) reached. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            # Return DONE with partial result instead of FAILED — user sees the last answer
            last_response = ""
            for m in reversed(messages):
                if m["role"] == "assistant" and m["content"].strip():
                    last_response = m["content"]
                    break
            from agent_core.reasoning import strip_reasoning_markers
            clean = strip_reasoning_markers(last_response) if last_response else "The task could not be completed within the turn limit."
            await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": clean, "status": "partial"})

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Critical error in execution loop: {e}. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "critical_failure", "error": str(e)})

    async def run_forever(self):
        self._running = True
        logger.info(f"ExecutorAgentWorker started (listening on A2A bus topic: {AgentRole.SPECIALIST.value})")
        
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
                logger.error(f"Error processing A2A message: {e}")
