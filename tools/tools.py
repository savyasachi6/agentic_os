"""
Tool registry and built-in tools for the ReAct agent loop.
Refactored to OS-Level Kernel using Pydantic Models and a Sandboxed WorkspaceManager.
"""

import os
import json
import subprocess
from pydantic import BaseModel, Field
from typing import Dict, Any, Callable, Optional, Type

from rag.vector_store import VectorStore
from dev.projects.devops_auto import ci_runner, deploy, chat_bridge, pr_manager
from productivity import briefing, todo_manager, notes, task_planner
from core.settings import settings
from datetime import datetime


from .base import BaseAction, ActionResult
from .registry import registry


# ---------------------------------------------------------------------------
# 2. Sandboxing Layer
# ---------------------------------------------------------------------------
import pathlib

class WorkspaceManager:
    # Use environment variable or default to project root / tmp
    BASE_DIR = pathlib.Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()
    
    @classmethod
    def sanitize_path(cls, path: str) -> str:
        """Prevents directory traversal and symlink attacks"""
        try:
            target_path = pathlib.Path(cls.BASE_DIR, path).resolve(strict=False)
            if not target_path.is_relative_to(cls.BASE_DIR):
                raise PermissionError(f"Agent attempted to access forbidden path: {path}")
            return str(target_path)
        except Exception as e:
            raise PermissionError(f"Path resolution failed: {e}")


# BaseAction is now in .base


# ---------------------------------------------------------------------------
# 4. Built-in Sandboxed Actions
# ---------------------------------------------------------------------------
class ReadFileAction(BaseAction):
    name: str = "read_file"
    description: str = "Read the contents of a file within the secure workspace."
    parameters: str = "path: str"
    
    path: str = Field(default="", description="The relative path to the file you want to read.")

    def run(self) -> str:
        safe_path = WorkspaceManager.sanitize_path(self.path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError(f"File not found: {self.path} (Resolved: {safe_path})")
            
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 10_000:
            return content[:10_000] + f"\n... [truncated, total {len(content)} chars]"
        return content


class WriteFileAction(BaseAction):
    name: str = "write_file"
    description: str = "Write content to a file. Creates parent directories if needed."
    parameters: str = "path: str, content: str"
    
    path: str = Field(default="", description="The relative path to the file to create or overwrite.")
    content: str = Field(default="", description="The text content to write.")

    def run(self) -> str:
        safe_path = WorkspaceManager.sanitize_path(self.path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(self.content)
        return f"Written {len(self.content)} chars to {safe_path}"


class RunShellAction(BaseAction):
    name: str = "run_shell"
    description: str = "Execute a shell command and return its output."
    parameters: str = "cmd: str, timeout: int (default: 30)"
    
    cmd: str = Field(default="", description="The shell command to execute.")
    timeout: int = Field(default=30, description="Max execution time in seconds.")

    def run(self) -> str:
        # Safety enforcement (basic example, can be expanded)
        banned = ("rm -rf /", "mkfs", "shutdown")
        if any(b in self.cmd for b in banned):
            raise PermissionError("Command blocked for safety reasons.")
            
        result = subprocess.run(
            self.cmd, shell=True, capture_output=True, text=True, timeout=self.timeout, cwd=WorkspaceManager.BASE_DIR
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
            
        if len(output) > 5_000:
            output = output[:5_000] + "\n... [truncated]"
        return output.strip() or "(no output)"


class ListDirAction(BaseAction):
    name: str = "list_dir"
    description: str = "List the files and directories in a given path."
    parameters: str = "path: str (default: current dir)"
    
    path: str = Field(default=".", description="Path to list")

    def run(self) -> str:
        safe_path = WorkspaceManager.sanitize_path(self.path)
        if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
            raise NotADirectoryError(f"Directory not found: {self.path}")
            
        entries = sorted(os.listdir(safe_path))
        lines = []
        for e in entries[:100]:
            full = os.path.join(safe_path, e)
            kind = "dir" if os.path.isdir(full) else "file"
            lines.append(f"  {kind}  {e}")
        result = f"Contents of {self.path}:\n" + "\n".join(lines)
        if len(entries) > 100:
            result += f"\n  ... and {len(entries) - 100} more"
        return result


# ---------------------------------------------------------------------------
# Skill/RAG Tools
# ---------------------------------------------------------------------------
_vs: Optional[VectorStore] = None

def _get_vs() -> VectorStore:
    global _vs
    if _vs is None:
        _vs = VectorStore()
    return _vs

class SkillSearchAction(BaseAction):
    name: str = "skill_search"
    description: str = "Search the indexed skill database by semantic similarity. You can request more detailed context by increasing the count."
    parameters: str = "query: str, count: int (default: 5)"
    
    query: str = Field(default="", description="Search query")
    count: int = Field(default=5, description="Number of results to retrieve")

    def run(self) -> str:
        results, _ = _get_vs().search_skills_relational(self.query, limit=self.count)
        if not results:
            return "No matching skills found."
        lines = []
        for r in results:
            rel = "[RELATIONAL] " if r.get("is_relational") else ""
            lines.append(f"--- {rel}Skill: {r['skill_name']} ({r['chunk_type']}) ---")
            lines.append(r['content'])
            lines.append("")
        return "\n".join(lines)


class RagQueryAction(BaseAction):
    name: str = "rag_query"
    description: str = "Search long-term agent memory (past thoughts, observations) by semantic similarity."
    parameters: str = "query: str"
    
    query: str = Field(default="", description="Search query")

    def run(self) -> str:
        results = _get_vs().search_thoughts(self.query, limit=5)
        if not results:
            return "No relevant memories found."
        lines = []
        for r in results:
            lines.append(f"- [{r['role']}] (score={r['score']:.3f}): {r['content'][:200]}...")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# General Fallback Action Wrapper (for existing functions like deploy)
# ---------------------------------------------------------------------------
class PythonFnAction(BaseAction):
    """Wraps an arbitrary python function inside the Pydantic BaseAction signature."""
    fn: Callable = Field(exclude=True, default=lambda: "")
    
    def run(self) -> str:
        # For legacy functions that aren't natively defining Fields
        # We rely on kwargs injected manually via execute(**kwargs) -> run_action(**kwargs)
        # But this implies a structural mismatch if run_action parses self__class__(**kwargs).
        # We handle this case by overriding run_action manually for legacy python fn wrappers.
        pass
        
    def run_action(self, **kwargs) -> ActionResult:
        try:
            res = self.fn(**kwargs)
            return ActionResult(success=True, data={"output": str(res)})
        except Exception as e:
            return ActionResult(success=False, data={}, error_trace=str(e), suggested_retry=True)


def build_tool_registry():
    # Placeholder for backward compatibility
    return registry.tools

# Registration
tools_to_register = [
    ReadFileAction(), WriteFileAction(), ListDirAction(), RunShellAction(),
    SkillSearchAction(), RagQueryAction()
]
for t in tools_to_register:
    registry.register(t)

# Legacy functional tools (skipped for brevity, but they should be wrapped)


def format_tool_descriptions(registry: Dict[str, BaseAction]) -> str:
    """Format tool descriptions for inclusion in the system prompt."""
    lines = ["You have access to the following Action Registry Tools:\n"]
    for name, tool in registry.items():
        lines.append(f"- **{name}**({tool.parameters}): {tool.description}")
    lines.append(
        "\nTo use a tool, output:\n"
        "Action: tool_name(arg1=value1, arg2=value2)\n"
        "Then wait for the ActionResult.\n"
    )
    return "\n".join(lines)
