"""
Logic for mapping intent or legacy tools to specialist agent types.
"""

def route_action_to_agent(action_name: str) -> str:
    """
    Maps an interpreted action name to a strict agent_type queue topic.
    """
    action_name = action_name.lower().strip()
    
    if action_name in ["sql", "sql_query", "database", "db_query"]:
        return "sql"
    elif action_name in ["research", "search", "web_search", "rag", "web_fetch", "web_navigate", "browser_navigate"]:
        return "research"
    elif action_name in ["code", "run_shell", "read_file", "write_file", "python", "run_python"]:
        return "code"
    elif action_name in ["respond", "finish", "done", "complete", "complete_task"]:
        return "respond"
        
    # Default to code agent for unmapped generic system actions to preserve sandboxing
    return "code"
