"""
core/reasoning.py
=================
Core logic for parsing LLM thoughts and actions.
Replaces agent_core/loop/thought_loop.py.
"""
import re
import logging
import json
from typing import Optional, Tuple

logger = logging.getLogger("agentos.core.reasoning")

def parse_react_action(response_text: str) -> Optional[Tuple[str, str]]:
    """
    Parses a ReAct response block looking for `Action: <agent_type>(<goal>)`
    or a JSON block like `{"action": "...", "content": "..."}`.
    """
    # 1. Try JSON parsing
    try:
        if response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            data = json.loads(response_text)
            action = data.get("action")
            payload = data.get("content") or data.get("goal") or data.get("payload")
            if action and payload:
                return str(action), str(payload)
    except Exception:
        pass

    # 2. Traditional ReAct parsing
    header_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response_text)
    if not header_match:
        return None
    
    action_type = header_match.group(1).strip()
    
    # Simple balanced paren/brace extraction
    start_pos = header_match.end()
    remaining = response_text[start_pos:]
    m_bracket = re.search(r"[\(\{\[]", remaining)
    
    if not m_bracket:
        return None
        
    bracket = m_bracket.group(0)
    # Balanced bracket extraction for the payload
    # Find the matching closing bracket
    stack = []
    end_pos = -1
    for i, char in enumerate(remaining):
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            if not stack: continue
            top = stack.pop()
            if (top == "(" and char == ")") or \
               (top == "{" and char == "}") or \
               (top == "[" and char == "]"):
                if not stack:
                    end_pos = i
                    break
    
    if end_pos == -1:
        return None
        
    payload = remaining[m_bracket.start() + 1 : end_pos].strip()
    
    # 3. Cleanup: Strip common prefixes like message="..." or content="..."
    # This ensures respond_direct(message="Hello") returns "Hello" instead of 'message="Hello"'
    prefixes = ['message=', 'content=', 'payload=', 'goal=', 'task=', 'query=', 'command=']
    for prefix in prefixes:
        if payload.lower().startswith(prefix):
            inner = payload[len(prefix):].strip()
            # Strip surrounding quotes if they exist
            if len(inner) >= 2 and ((inner[0] == '"' and inner[-1] == '"') or (inner[0] == "'" and inner[-1] == "'")):
                payload = inner[1:-1]
            else:
                payload = inner
            break

    return action_type, payload

def parse_thought(response_text: str) -> str:
    """Extracts the reasoning thought from the response."""
    match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()
