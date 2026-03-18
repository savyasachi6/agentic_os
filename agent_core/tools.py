"""
Tool registry and built-in tools for the ReAct agent loop.

Each tool is a callable with a name, description, and parameter schema.
The registry maps tool names to their implementations for dispatch.
"""

import os
import subprocess
from typing import Dict, Any, Callable, Optional

from agent_memory.vector_store import VectorStore
from devops_auto import ci_runner, deploy, chat_bridge, pr_manager
from productivity import briefing, todo_manager, notes, task_planner
from agent_config import devops_settings, productivity_settings


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------
class Tool:
    def __init__(self, name: str, description: str, parameters: str, fn: Callable, risk_level: str = "low"):
        self.name = name
        self.description = description
        self.parameters = parameters  # human-readable param spec for the LLM
        self.fn = fn
        self.risk_level = risk_level

    def execute(self, **kwargs) -> str:
        try:
            return str(self.fn(**kwargs))
        except Exception as e:
            return f"[Tool Error] {self.name}: {e}"


# ---------------------------------------------------------------------------
# Built-in tool implementations
# ---------------------------------------------------------------------------
def _read_file(path: str) -> str:
    """Read and return the contents of a file."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return f"File not found: {path}"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    # Truncate very large files
    if len(content) > 10_000:
        return content[:10_000] + f"\n... [truncated, total {len(content)} chars]"
    return content


def _write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed."""
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written {len(content)} chars to {path}"


def _run_shell(cmd: str, timeout: int = 30) -> str:
    """Execute a shell command with a timeout. Returns stdout + stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        # Truncate
        if len(output) > 5_000:
            output = output[:5_000] + "\n... [truncated]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[Tool Error] Command timed out after {timeout}s"


def _list_dir(path: str = ".") -> str:
    """List the contents of a directory."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return f"Not a directory: {path}"
    entries = sorted(os.listdir(path))
    lines = []
    for e in entries[:100]:
        full = os.path.join(path, e)
        kind = "dir" if os.path.isdir(full) else "file"
        lines.append(f"  {kind}  {e}")
    result = f"Contents of {path}:\n" + "\n".join(lines)
    if len(entries) > 100:
        result += f"\n  ... and {len(entries) - 100} more"
    return result


# Skill/RAG tools need a VectorStore instance — created lazily
_vs: Optional[VectorStore] = None


def _get_vs() -> VectorStore:
    global _vs
    if _vs is None:
        _vs = VectorStore()
    return _vs


def _skill_search(query: str) -> str:
    """Search indexed skills by semantic similarity."""
    results = _get_vs().search_skills(query, limit=5)
    if not results:
        return "No matching skills found."
    lines = []
    for r in results:
        lines.append(f"- [{r['skill_name']}] ({r['chunk_type']}, score={r['score']:.3f}): {r['content'][:200]}...")
    return "\n".join(lines)


def _rag_query(query: str) -> str:
    """Search agent thoughts and long-term memory."""
    results = _get_vs().search_thoughts(query, limit=5)
    if not results:
        return "No relevant memories found."
    lines = []
    for r in results:
        lines.append(f"- [{r['role']}] (score={r['score']:.3f}): {r['content'][:200]}...")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def build_tool_registry() -> Dict[str, Tool]:
    """Create the default set of built-in tools."""
    tools = [
        Tool(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters="path: str",
            fn=_read_file,
        ),
        Tool(
            name="write_file",
            description="Write content to a file. Creates parent directories if needed.",
            parameters="path: str, content: str",
            fn=_write_file,
        ),
        Tool(
            name="list_dir",
            description="List the files and subdirectories in a directory.",
            parameters="path: str (default: current dir)",
            fn=_list_dir,
        ),
        Tool(
            name="run_shell",
            description="Execute a shell command and return its output. Use for running scripts, installing packages, etc.",
            parameters="cmd: str, timeout: int (default: 30)",
            fn=_run_shell,
        ),
        Tool(
            name="skill_search",
            description="Search the indexed skill database by semantic similarity. Use when you need to find a relevant skill.",
            parameters="query: str",
            fn=_skill_search,
        ),
        Tool(
            name="rag_query",
            description="Search long-term agent memory (past thoughts, observations) by semantic similarity.",
            parameters="query: str",
            fn=_rag_query,
            risk_level="low",
        ),
        Tool(
            name="list_processes",
            description="List top processes by CPU/memory usage.",
            parameters="top_n: int (default: 20)",
            fn=lambda top_n=20: "System call initiated via sandbox.",
            risk_level="low",
        ),
        Tool(
            name="get_system_info",
            description="Get host system information (OS, CPU, Memory).",
            parameters="",
            fn=lambda: "System call initiated via sandbox.",
            risk_level="low",
        ),
        Tool(
            name="get_event_logs",
            description="Retrieve recent system or application event logs.",
            parameters="source: str (default: System), last_n: int (default: 10)",
            fn=lambda source="System", last_n=10: "System call initiated via sandbox.",
            risk_level="low",
        ),
        Tool(
            name="get_gpu_stats",
            description="Get GPU utilization stats (nvidia-smi).",
            parameters="",
            fn=lambda: "System call initiated via sandbox.",
            risk_level="low",
        ),
        # --- DevOps Tools ---
        Tool(
            name="run_tests",
            description="Run a test suite command in a specific directory.",
            parameters="cmd: str, cwd: str, timeout: int = 300",
            fn=ci_runner.run_tests,
            risk_level="medium",
        ),
        Tool(
            name="deploy",
            description="Deploy a specific image tag to a target environment.",
            parameters="target: str (staging/prod), image_tag: str",
            fn=lambda target, image_tag: deploy.deploy_to_staging(
                deploy.DeploymentConfig(target=target, image_tag=image_tag)
            ),
            risk_level="high",
        ),
        Tool(
            name="send_telegram",
            description="Send an alert or message to the configured Telegram chat.",
            parameters="chat_id: str, text: str",
            fn=lambda chat_id, text: chat_bridge.TelegramBridge(
                token=devops_settings.telegram_token
            ).send(chat_id, text) if devops_settings.telegram_token else "Telegram token not configured.",
            risk_level="low",
        ),
        Tool(
            name="create_pull_request",
            description="Create a new branch, apply changes, and push to origin.",
            parameters="repo_path: str, branch_name: str, message: str, patches: list[dict]",
            fn=lambda repo_path, branch_name, message, patches: (
                pr_manager.create_branch(repo_path, branch_name) and 
                pr_manager.apply_changes(repo_path, patches) and 
                pr_manager.commit_and_push(repo_path, message)
            ),
            risk_level="medium",
        ),
        # --- Productivity Tools ---
        Tool(
            name="get_morning_briefing",
            description="Get an overview of today's tasks, weather, and calendar.",
            parameters="",
            fn=lambda: briefing.format_briefing(
                briefing.generate_briefing(
                    datetime.now(), 
                    todo_manager.TodoManager().get_due_today(),
                    [] 
                )
            ),
            risk_level="low",
        ),
        Tool(
            name="manage_todo",
            description="Add, list, or update to-do items.",
            parameters="action: str (add/list/update), title: str = None, priority: int = 1, status: str = None",
            fn=lambda action, **kwargs: str(todo_manager.TodoManager().add_todo(kwargs.get('title'), kwargs.get('priority')) if action == 'add' else "TODO Action performed"),
            risk_level="low",
        ),
        Tool(
            name="search_notes",
            description="Search personal notes and knowledge base.",
            parameters="query: str",
            fn=lambda query: notes.NoteManager(None).query_notes(query, None),
            risk_level="low",
        ),
    ]
    return {t.name: t for t in tools}


def format_tool_descriptions(registry: Dict[str, Tool]) -> str:
    """Format tool descriptions for inclusion in the system prompt."""
    lines = ["You have access to the following tools:\n"]
    for name, tool in registry.items():
        lines.append(f"- **{name}**({tool.parameters}): {tool.description}")
    lines.append(
        "\nTo use a tool, output:\n"
        "Action: tool_name(arg1=value1, arg2=value2)\n"
        "Then wait for the Observation.\n"
    )
    return "\n".join(lines)
