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

from core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agents.graph.state import AgentState
from core.agent_types import Intent, AgentRole, NodeStatus
from core.guards import is_safe_command
from core.message_bus import A2ABus

logger = logging.getLogger("agentos.agents.executor")

from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.executor")

class ExecutorAgentWorker(AgentWorker):
    """
    Background worker that handles generic specialist tasks (AgentRole.SPECIALIST).
    """
    def __init__(self, store: TreeStore = None, model_name: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.role = AgentRole.SPECIALIST
        self.system_prompt = ""
        self._load_prompt()
        
        # Initialize parent worker with this role and current instance as the agent
        super().__init__(role=self.role, agent=self, store=store or TreeStore())

    def _load_prompt(self):
        from prompts.loader import load_prompt
        try:
            self.system_prompt = load_prompt("executor")
        except Exception as e:
            logger.error(f"Failed to load executor prompt: {e}")
            self.system_prompt = "You are the ExecutorAgent. Use shell_execute for CLI tasks or respond() to finish."

    async def _process_task(self, task: Node):
        from core.reasoning import parse_react_action
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
        session_id = task.payload.get("session_id", "default")
        
        try:
            for i in range(max_iterations):
                # Check for abandonment (Phase 5 Hardening)
                current = await self.tree_store.get_node_by_id_async(task.id)
                if not current or current.status not in (NodeStatus.PENDING, NodeStatus.RUNNING):
                    logger.warning(f"Task {task.id} abandoned by coordinator. Aborting specialist loop. node_id={task.id}")
                    return

                logger.info(f"Turn {i+1}/{max_iterations}: Starting LLM streaming generation...")
                
                response_text = ""
                turn_label = f"**[Executor Turn {i+1}/{max_iterations}]** "
                first_thought = True

                async for chunk in self.llm.generate_streaming(messages, session_id=session_id):
                    chunk_type = chunk.get("type")
                    content = chunk.get("content", "")
                    
                    if chunk_type == "thought":
                        if first_thought:
                            content = turn_label + content
                            first_thought = False
                        
                        await self.bus.publish(AgentRole.SPECIALIST.value, {
                            "type": "thought",
                            "content": content,
                            "session_id": session_id
                        })
                    elif chunk_type == "token":
                        response_text += content
                        await self.bus.publish(AgentRole.SPECIALIST.value, {
                            "type": "token",
                            "content": content,
                            "session_id": session_id
                        })
                    elif chunk_type == "error":
                        logger.error(f"Streaming error on turn {i+1}: {content}")
                        break

                messages.append({"role": "assistant", "content": response_text})
                
                action_data = parse_react_action(response_text)
                if not action_data:
                    duration = time.time() - start_time
                    logger.info(f"No action parsed. Completing task. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"message": response_text})
                    return

                action_type, action_payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")
                
                if action_type in ["respond", "done", "complete", "finish"]:
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
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "max_turns", "error": "Max iterations reached without completing."})

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
