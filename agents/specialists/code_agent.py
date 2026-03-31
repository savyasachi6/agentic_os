"""
agents/code_agent.py
====================
Refactored CodeAgentWorker using the modular folder structure.
Handles file operations, diffs, and shell commands in a safe sandbox.
Depends on db.queries.commands, db.models, and core.types.
"""
import os
import logging
import re
import json
import asyncio
import subprocess
from core.message_bus import A2ABus
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from core.llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agents.graph.state import AgentState
from core.agent_types import Intent, AgentRole, NodeStatus
from core.cache import FractalCache

logger = logging.getLogger("agentos.agents.code")

# Prohibited shell command prefixes (safety layer)
_BANNED_COMMANDS = ("rm ", "del ", "rmdir", "format ", "mkfs", "shutdown", "reboot",
                    "dd ", "truncate", ":(){", "DROP TABLE", "DROP DATABASE")

def _is_safe_command(cmd: str) -> bool:
    """Block destructive shell commands."""
    c = cmd.strip().lower()
    return not any(c.startswith(b.lower()) or b.lower() in c for b in _BANNED_COMMANDS)

from core.reasoning import parse_react_action, strip_all_reasoning

from agents.worker import AgentWorker

logger = logging.getLogger("agentos.agents.code")

class CodeAgentWorker(AgentWorker):
    """
    Background worker that handles file operations and CLI tools (AgentRole.TOOLS).
    """
    def __init__(self, store: TreeStore = None, model_name: Optional[str] = None, workspace_root: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.role = AgentRole.TOOLS
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()
        self.system_prompt = ""
        self._load_prompt()
        
        # Initialize parent worker with this role and current instance as the agent
        super().__init__(role=self.role, agent=self, store=store or TreeStore())

    def _load_prompt(self):
        from prompts.loader import load_prompt
        try:
            self.system_prompt = load_prompt("code")
        except Exception as e:
            logger.error(f"Failed to load code prompt: {e}")
            self.system_prompt = "You are the CodeAgent. Read files, propose diffs, write files safely."

    # --- Tool implementations ---
    def _read_file(self, path: str) -> str:
        try:
            p = Path(path).resolve()
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"[CodeAgentWorker] Failed to read file {path}: {e}")
            return f"[Error reading file: {e}]"

    def _list_dir(self, path: str) -> str:
        try:
            p = Path(path).resolve()
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = []
            for entry in entries[:50]:
                tag = "F" if entry.is_file() else "D"
                size = f" ({entry.stat().st_size}B)" if entry.is_file() else ""
                lines.append(f"[{tag}] {entry.name}{size}")
            return "\n".join(lines) or "(empty)"
        except Exception as e:
            logger.error(f"[CodeAgentWorker] Failed to list dir {path}: {e}")
            return f"[Error listing dir: {e}]"

    def _run_command(self, cmd: str) -> str:
        if not _is_safe_command(cmd):
            return f"[BLOCKED] Command not permitted for safety: {cmd}"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=15, cwd=str(self.workspace_root)
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            if err:
                return f"stdout:\n{out}\nstderr:\n{err}"
            return out or "(no output)"
        except subprocess.TimeoutExpired:
            return "[Error: command timed out after 15s]"
        except Exception as e:
            logger.error(f"[CodeAgentWorker] Failed to run command {cmd}: {e}")
            return f"[Error running command: {e}]"

    def _write_file(self, path: str, content: str) -> str:
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"[Written {len(content)} chars to {p}]"
        except Exception as e:
            logger.error(f"[CodeAgentWorker] Failed to write file {path}: {e}")
            return f"[Error writing file: {e}]"

    # --- Main task processor ---
    async def _process_task(self, task: Node):
        import time
        start_time = time.time()
        goal = task.payload.get("query", task.payload.get("goal", "Unknown Goal"))
        logger.info(f"Task received: node_id={task.id}, role={AgentRole.TOOLS.value}, goal='{goal[:50]}...'")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task Goal: {goal}\n\nWorkspace root: {self.workspace_root}"}
        ]

        try:
            max_iterations = 6
            for i in range(max_iterations):
                logger.info(f"Turn {i+1}/{max_iterations}: Starting Code streaming...")
                
                response_text = ""
                turn_label = f"**[Code Turn {i+1}/{max_iterations}]** "
                first_thought = True

                async for chunk in self.llm.generate_streaming(messages, session_id=str(task.chain_id)):
                    chunk_type = chunk.get("type")
                    content = chunk.get("content", "")
                    
                    if chunk_type == "thought":
                        if first_thought and content:
                            content = turn_label + content
                            first_thought = False
                        
                        await self.bus.publish(self.role.value, {"type": "thought", "content": content})
                    elif chunk_type == "token":
                        response_text += content
                        await self.bus.publish(self.role.value, {"type": "token", "content": content})
                    elif chunk_type == "error":
                        logger.error(f"Streaming error: {content}")
                        break

                if not response_text or not response_text.strip():
                    logger.warning(f"LLM returned no content on turn {i+1}. node_id={task.id}")
                    # Phase 5.1: Defensive turn retry
                    if i < 3: # Allow retries on early turns
                        await self.bus.publish(self.role.value, {
                            "type": "thought", 
                            "content": f"System is waiting for a more complete response on turn {i+1}... (Retrying)"
                        })
                        await asyncio.sleep(3)
                        continue
                    else:
                        await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "no_content", "error": f"LLM failed to produce content on turn {i+1} after retries."})
                        return

                messages.append({"role": "assistant", "content": response_text})

                action_data = parse_react_action(response_text)
                if not action_data:
                    # Fallback: Extract bare code block IF it's likely the intended result
                    # and no other ReAct headers are present (Correctness Fix)
                    if "Thought:" not in response_text and "Action:" not in response_text:
                        code_match = re.search(r"```(?:python)?\n(.*?)\n```", response_text, re.DOTALL)
                        if code_match:
                            action_data = ("write_file", f"generated_code.py|{code_match.group(1).strip()}")
                    
                    if not action_data:
                        duration = time.time() - start_time
                        logger.error(f"Parse error. node_id={task.id}, duration={duration:.2f}s")
                        assert task.id is not None
                        await self.tree_store.update_node_status_async(
                            task.id, NodeStatus.FAILED,
                            result={"error_type": "parse_error", "error": "Could not parse a valid Action from response"}
                        )
                        return

                action_type, payload = action_data
                logger.info(f"Turn {i+1}: Action parsed: {action_type}")

                if action_type in ("complete", "done", "respond", "finish"):
                    duration = time.time() - start_time
                    logger.info(f"Task completed. node_id={task.id}, duration={duration:.2f}s")
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"summary": payload})
                    return

                elif action_type == "read_file":
                    loop = asyncio.get_running_loop()
                    obs = await loop.run_in_executor(None, self._read_file, payload)
                elif action_type == "list_dir":
                    loop = asyncio.get_running_loop()
                    obs = await loop.run_in_executor(None, self._list_dir, payload)
                elif action_type == "write_file":
                    parts = payload.split("|", 1)
                    if len(parts) == 2:
                        path, content = parts[0].strip(), parts[1].strip()
                        loop = asyncio.get_running_loop()
                        obs = await loop.run_in_executor(None, self._write_file, path, content)
                    else:
                        obs = "[Error: write_file requires path|content format]"
                elif action_type == "run_command":
                    loop = asyncio.get_running_loop()
                    obs = await loop.run_in_executor(None, self._run_command, payload)
                elif action_type in ["web_search", "hybrid_search", "web_scrape"]:
                    obs = f"Observation: [Tool Access Denied] The Code Specialist is restricted to filesystem and execution tools. For web search or RAG research, please use 'complete' with a request for the RAG agent or focus on code tasks."
                else:
                    obs = f"Observation: [Unknown action: {action_type}]. Available tools: read_file, list_dir, write_file, run_command, complete."

                messages.append({"role": "user", "content": f"Observation: {obs}"})

            duration = time.time() - start_time
            logger.warning(f"Exceeded max iterations. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, NodeStatus.FAILED,
                result={"error_type": "max_turns", "error": "Exceeded max iterations without completing."}
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Critical error in execution loop: {e}. node_id={task.id}, duration={duration:.2f}s")
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error_type": "critical_failure", "error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        logger.info(f"CodeAgentWorker started (polling TreeStore for role: {AgentRole.TOOLS.value})")
        while self._running:
            try:
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.TOOLS)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(poll_interval)
