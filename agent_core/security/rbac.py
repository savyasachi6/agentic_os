def get_required_scope_for_tool(level: str) -> str:
    """Return the scope string required for a given tool level (low, high, etc)."""
    return f"tool:{level}"
