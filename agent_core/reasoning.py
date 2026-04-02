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

# Patterns that indicate the LLM echoed template/placeholder text instead of
# generating a real answer. If the payload matches any of these (case-insensitive),
# the parse is rejected so the coordinator falls through to fallback handling.
_PLACEHOLDER_PATTERNS = {
    "[your complete answer]",
    "[your answer]",
    "[your answer here]",
    "[your complete answer here]",
    "<write your full answer here>",
    "write your full, detailed answer here — never leave this blank or use placeholder text",
    "write your answer here",
    "your actual, complete answer text goes here",
}

def _is_placeholder(text: str) -> bool:
    """Return True if text is a known prompt-template placeholder."""
    stripped = text.strip().lower()
    return stripped in _PLACEHOLDER_PATTERNS or stripped == ""

def parse_react_action(response_text: str) -> Optional[Tuple[str, str]]:
    """
    Parses a ReAct response block looking for `Action: <agent_type>(<goal>)`
    or a JSON block like `{"action": "...", "content": "..."}`.
    """
    # 1. Triple-quote respond_direct (Phase 102 Hardening)
    # This is the highest priority for final results.
    # Matches: Action: respond_direct(message="""\n...\n""")
    tq_match = re.search(
        r'Action:\s*respond_direct\s*\(\s*message\s*=\s*"""(.*?)"""\s*\)',
        response_text,
        re.DOTALL
    )
    if tq_match:
        return "respond_direct", tq_match.group(1).strip()

    # 2. Try JSON parsing
    try:
        if response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            data = json.loads(response_text)
            action = data.get("action")
            payload = data.get("content") or data.get("goal") or data.get("payload")
            if action and payload:
                return str(action), str(payload)
    except Exception:
        pass

    # 3. Traditional ReAct parsing
    header_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response_text)
    if not header_match:
        # No Action: line found. Try "Final Answer:" as a last resort.
        fb = re.search(r'(?:Final Answer:)\s*(.*)', response_text, re.IGNORECASE | re.DOTALL)
        if fb:
            return "respond", fb.group(1).strip()
        return None
    
    action_type = header_match.group(1).strip()
    
    # Simple balanced paren/brace extraction
    start_pos = header_match.end()
    remaining = response_text[start_pos:]
    
    # 3. Extract Payload (balanced brackets with quote-awareness)
    m_bracket = re.search(r"\(", remaining)
    if not m_bracket:
        return None
        
    stack = 1
    end_pos = -1
    in_quote = None  # Tracks if we are inside "..." or '...'
    
    for i in range(m_bracket.start() + 1, len(remaining)):
        char = remaining[i]
        
        # Handle Quotes
        if char in ('"', "'"):
            if not in_quote:
                in_quote = char
            elif in_quote == char:
                # Basic check for escaped quote: \" (though LLMs rarely use it)
                if i > 0 and remaining[i-1] != "\\":
                    in_quote = None
        
        # Only track brackets if NOT inside a quote
        if not in_quote:
            if char == "(":
                stack += 1
            elif char == ")":
                stack -= 1
                if stack == 0:
                    end_pos = i
                    break
    
    if end_pos == -1:
        return None
        
    payload = remaining[m_bracket.start() + 1 : end_pos].strip()
    
    # 4. Cleanup: Strip common prefixes like message="..." or content="..."
    # This ensures respond_direct(message="Hello") returns "Hello" instead of 'message="Hello"'
    prefixes = ['message=', 'content=', 'payload=', 'goal=', 'task=', 'query=', 'command=', 'answer=']
    for prefix in prefixes:
        if payload.lower().startswith(prefix):
            inner = payload[len(prefix):].strip()
            # Strip surrounding quotes if they exist
            if len(inner) >= 2 and ((inner[0] == '"' and inner[-1] == '"') or (inner[0] == "'" and inner[-1] == "'")):
                payload = inner[1:-1]
            else:
                payload = inner
            break

    # 5. Placeholder guard: reject literal template text
    if _is_placeholder(payload):
        logger.warning("Rejected placeholder payload from LLM: %s", payload[:80])
        return None

    return action_type, payload

def parse_thought(response_text: str) -> str:
    """
    Extracts the reasoning thought from the response.
    Harden: Only capture as a 'thought' if an 'Action:' block follows it, 
    otherwise it's likely the final answer itself.
    """
    # 1. Flexible lookahead for Action: (case insensitive, optional newline)
    match = re.search(r"Thought:\s*(.*?)(?=\s*Action:)", response_text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 2. If no Action: found, it might be a direct answer. 
    # Do NOT treat the whole thing as a thought if it lacks the Thought: prefix.
    if response_text.strip().lower().startswith("thought:"):
        return response_text.strip()[8:].strip()
    
    return ""

def strip_reasoning_markers(text: str) -> str:
    """
    Strips 'Thought:' and 'Action:' prefixes/blocks from a final response 
    to provide a clean output to the user.
    """
    # Priority: extract respond_direct payload if present
    tq = re.search(
        r'Action:\s*respond_direct\s*\(\s*message\s*=\s*"""(.*?)"""\s*\)',
        text,
        re.DOTALL
    )
    if tq:
        return tq.group(1).strip()

    # Remove tool Action: lines only — NOT with re.DOTALL
    text = re.sub(r'\nAction:\s*(?!respond_direct)[^\n]*', '', text)
    # Remove Thought: prefix lines
    text = re.sub(r'(?m)^Thought:\s*', '', text)
    return text.strip()

def normalize_thought(thought_text: Optional[str]) -> str:
    """
    Robustly clean internal model turn markers and normalize whitespace.
    Strips variants like **[Turn 1/4]**, [Turn 1 / 4], Thought: [Turn 1/4], etc.
    """
    if not thought_text:
        return ""
    
    import re as _re
    text = thought_text
    
    # 1. Multi-line/Inline repeated turn marker stripping (Power Regex)
    # Handles: bolding, spacing, brackets, and case-insensitivity any location (Global)
    # Matches: [Turn 1/5], [Iteration 2 / 10], **Step 1/3**, etc.
    text = _re.sub(r"(?i)(?:\*\*)?\\[?\s*(?:turn|iteration|step)\s+\d+\s*/\s*\d+\s*\\]?(?:\*\*)?:?\s*", "", text)
    
    # 2. Normalize whitespace (Max two newlines, max one space)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = _re.sub(r"[ \t]{2,}", " ", text)
    
    return text.strip()
