"""
intent/routing.py
=================
Maps interpreted action names (e.g., from LLM ReAct output) to specific specialist agents.
Replaces agent_core/loop/routing.py.
"""

_RESEARCH_KEYWORDS = {
    "research", "search", "web_search", "rag", "web_fetch", "browse",
    "investigate", "lookup", "retrieve", "hybrid_search", "speculative_rag",
    "news", "weather", "query", "status"
}

_CODE_KEYWORDS = {
    "code", "run_shell", "read_file", "write_file", "python", "execute", "shell_execute"
}

def route_action_to_agent(action_name: str) -> str:
    """
    Map an action name string to an agent role identifier.
    """
    normalized = action_name.lower().strip()

    if normalized in ["sql", "sql_query", "database", "db_query", "capability"]:
        return "capability"

    if any(kw in normalized for kw in _RESEARCH_KEYWORDS) or "search" in normalized or normalized == "rag":
        return "research"

    if normalized in _CODE_KEYWORDS or normalized == "code":
        return "code"

    if normalized in ["email", "send_email", "mail"]:
        return "email"

    if normalized in ["productivity", "todo", "calendar"]:
        return "productivity"

    if normalized in ["memory", "recall", "history"]:
        return "memory"

    if normalized == "planner":
        return "planner"

    if normalized in ["tool_caller", "calculate", "math", "evaluate", "calculator", "tool"]:
        return "tool_caller"

    if normalized in ["respond", "finish", "done", "complete", "respond_direct"]:
        return "respond"

    # Default to executor for safety
    return "executor"
