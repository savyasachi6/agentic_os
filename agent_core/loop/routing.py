"""
Logic for mapping intent or legacy tools to specialist agent types.
"""

# Research-related keywords the coordinator LLM commonly generates
_RESEARCH_KEYWORDS = {
    "research", "search", "web_search", "rag", "web_fetch", "web_navigate",
    "browser_navigate", "browse", "browsing", "web_browse", "investigate",
    "lookup", "look_up", "find", "fetch", "retrieve", "query_web",
    "internet_search", "online_search", "news", "current_events",
    "hybrid_search", "speculative_rag", "web_research", "google",
    "web", "navigator", "information_retrieval",
}

_RESEARCH_SUBSTRINGS = ("search", "web", "browse", "research", "fetch", "lookup", "retrieve")


def route_action_to_agent(action_name: str) -> str:
    """
    Maps an interpreted action name to a strict agent_type queue topic.
    """
    normalized = action_name.lower().strip()

    if normalized in ["sql", "sql_query", "database", "db_query"]:
        return "sql"

    if normalized in _RESEARCH_KEYWORDS:
        return "research"

    # Substring catch-all: anything that sounds web/search-related → research
    if any(sub in normalized for sub in _RESEARCH_SUBSTRINGS):
        return "research"

    if normalized in ["code", "run_shell", "read_file", "write_file", "python", "run_python", "execute"]:
        return "code"

    if normalized in ["email", "send_email", "mail", "send_mail"]:
        return "email"

    if normalized in ["respond", "finish", "done", "complete", "complete_task"]:
        return "respond"

    # Unknown action: log it and default to code for sandboxing safety
    print(f"[routing] Unrecognized action '{action_name}', defaulting to code agent.")
    return "code"
