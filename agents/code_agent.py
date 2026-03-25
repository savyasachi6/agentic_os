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
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from llm.client import LLMClient
from db.queries.commands import TreeStore
from db.models import Node
from agent_core.graph.state import AgentState
from agent_core.agent_types import Intent, AgentRole, NodeStatus
from agent_core.cache import FractalCache

logger = logging.getLogger("agentos.agents.code")

# Prohibited shell command prefixes (safety layer)
_BANNED_COMMANDS = ("rm ", "del ", "rmdir", "format ", "mkfs", "shutdown", "reboot",
                    "dd ", "truncate", ":(){", "DROP TABLE", "DROP DATABASE")

def _is_safe_command(cmd: str) -> bool:
    """Block destructive shell commands."""
    c = cmd.strip().lower()
    return not any(c.startswith(b.lower()) or b.lower() in c for b in _BANNED_COMMANDS)

def _parse_code_action(response_text: str) -> Optional[Tuple[str, str]]:
    """Extended balanced-paren parser for code actions."""
    header_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)\(", response_text)
    if not header_match:
        return None

    action_type = header_match.group(1).strip()
    start = header_match.end()
    depth = 1
    idx = start
    while idx < len(response_text) and depth > 0:
        ch = response_text[idx]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        idx += 1

    if depth != 0:
        return None

    payload = response_text[start:idx - 1].strip()
    return action_type, payload

class CodeAgent:
    """
    Background worker that polls the TreeStore for `AgentRole.TOOLS` nodes.
    Handles file read, diff proposal, write, and narrow shell command execution.
    """

    def __init__(self, model_name: Optional[str] = None, workspace_root: Optional[str] = None):
        self.llm = LLMClient(model_name=model_name)
        self.tree_store = TreeStore()
        # self.cache = FractalCache()
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()
        self.system_prompt: str = ""
        self._load_prompt()
        self._running = False

    def _load_prompt(self):
        # Adjusted path for refactored structure: llm/prompts/code_agent_prompt.md
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(root_dir, "prompts", "code.md")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
        else:
            self.system_prompt = "You are the CodeAgent. Read files, propose diffs, write files safely."

    # --- Tool implementations ---
    def _read_file(self, path: str) -> str:
        try:
            p = Path(path).resolve()
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("[CodeAgent] Failed to read file %s: %s", path, e)
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
            logger.error("[CodeAgent] Failed to list dir %s: %s", path, e)
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
            logger.error("[CodeAgent] Failed to run command %s: %s", cmd, e)
            return f"[Error running command: {e}]"

    def _write_file(self, path: str, content: str) -> str:
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"[Written {len(content)} chars to {p}]"
        except Exception as e:
            logger.error("[CodeAgent] Failed to write file %s: %s", path, e)
            return f"[Error writing file: {e}]"

    # --- Main task processor ---
    async def _process_task(self, task: Node):
        goal = task.payload.get("query", task.payload.get("goal", "Unknown Goal"))
        print(f"[CodeAgent] Received Task {task.id}: {goal}")

        # cached = await self.cache.get_cached_response_async(goal)
        # if cached:
        #     print(f"[CodeAgent] Cache hit. Resolving instantly.")
        #     assert task.id is not None
        #     await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result=cached["response"])
        #     return

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task Goal: {goal}\n\nWorkspace root: {self.workspace_root}"}
        ]

        try:
            max_iterations = 6
            for _ in range(max_iterations):
                response_text = await self.llm.generate_async(messages)
                messages.append({"role": "assistant", "content": response_text})

                action_data = _parse_code_action(response_text)
                if not action_data:
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(
                        task.id, NodeStatus.FAILED,
                        result={"error": "Could not parse a valid Action from response"}
                    )
                    return

                action_type, payload = action_data

                if action_type in ("complete", "done", "respond", "finish"):
                    # asyncio.create_task(self.cache.set_cached_response_async(
                    #     query=goal, response={"summary": payload}, strategy_used="code_worker"
                    # ))
                    assert task.id is not None
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"summary": payload})
                    print(f"[CodeAgent] Finished task {task.id}")
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
                else:
                    obs = f"[Unknown action: {action_type}]"

                messages.append({"role": "user", "content": f"Observation: {obs}"})

            assert task.id is not None
            await self.tree_store.update_node_status_async(
                task.id, NodeStatus.FAILED,
                result={"error": "Exceeded max iterations without completing."}
            )

        except Exception as e:
            logger.exception("[CodeAgent] Critical error processing task %s: %s", task.id, e)
            assert task.id is not None
            await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": str(e)})

    async def run_forever(self, poll_interval: float = 2.0):
        self._running = True
        print("[CodeAgent] Worker started.")
        while self._running:
            try:
                task = await self.tree_store.dequeue_task_async(agent_role=AgentRole.TOOLS)
                if task:
                    await self._process_task(task)
                else:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("[CodeAgent] Polling error: %s", e)
                await asyncio.sleep(poll_interval)
