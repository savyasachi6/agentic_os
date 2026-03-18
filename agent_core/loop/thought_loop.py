import re
from typing import Optional, Tuple


def parse_react_action(response_text: str) -> Optional[Tuple[str, str]]:
    """
    Parses a ReAct response block looking for `Action: <agent_type>(<goal>)`
    or a JSON block like `{"action": "...", "content": "..."}`.
    Returns a tuple of (agent_type, goal) or None if no action is found.
    """
    # 1. Try JSON parsing first for modern LLM outputs
    try:
        import json
        # Look for JSON-like structure
        if response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            data = json.loads(response_text)
            action = data.get("action")
            # Handle different common keys for the payload
            payload = data.get("content") or data.get("goal") or data.get("payload") or data.get("result")
            if action and payload:
                # If payload is a list of blocks (Claude style), join the text parts
                if isinstance(payload, list):
                    text_parts = [block.get("text", "") for block in payload if isinstance(block, dict) and block.get("type") == "text"]
                    payload = "\n".join(text_parts)
                return str(action), str(payload)
    except Exception:
        pass

    # 2. Traditional ReAct parsing: Action: <name>(<payload>)
    header_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response_text)
    if not header_match:
        return None
    
    action_type = header_match.group(1).strip()
    
    # Find the next non-whitespace character
    start_pos: int = int(header_match.end())
    
    # Use generator with index to bypass slicing errors in some type checkers
    remaining = "".join(response_text[i] for i in range(start_pos, len(response_text)))
    m_start = re.search(r"[\(\{\[]", remaining)
    
    if not m_start:
        return None
    
    char_start = m_start.group(0)
    actual_start = start_pos + m_start.start()
    
    if char_start == '(':
        # Balanced paren logic
        depth = 1
        idx = actual_start + 1
        while idx < len(response_text) and depth > 0:
            ch = response_text[idx]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            idx += 1
        
        if depth == 0:
            payload = "".join(response_text[i] for i in range(int(actual_start + 1), int(idx - 1))).strip()
            return action_type, payload
    
    elif char_start in ['{', '[']:
        # Balanced brace logic for JSON payload on new line or same line
        depth = 1
        idx = actual_start + 1
        while idx < len(response_text) and depth > 0:
            ch = response_text[idx]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
            idx += 1
            
        if depth == 0:
            payload = "".join(response_text[i] for i in range(int(actual_start), int(idx))).strip()
            return action_type, payload
            
    return None


def parse_thought(response_text: str) -> str:
    """Extracts the reasoning thought from the response."""
    # 1. Try JSON parsing first
    try:
        import json
        if response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            data = json.loads(response_text)
            thought = data.get("thought") or data.get("reasoning") or data.get("Thought")
            if thought:
                return str(thought).strip()
    except Exception:
        pass

    # 2. Traditional regex parsing
    match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Fallback to returning the entire response if it doesn't strictly match the prefix
    return response_text.strip()
