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
    Parses a ReAct response block looking for `Action: <agent_type>(<goal>)`,
    XML-style `<action>...</action>` tags, or a JSON block.
    """
    # 1. Try XML-style parsing (most reliable for modern models)
    # Phase 55: Explicitly support tags that might be nested or have leading/trailing whitespace
    xml_match = re.search(r"<action>\s*([a-zA-Z0-9_\-]+)\s*[\(\{\[](.*?)[\)\}\]]\s*</action>", response_text, re.DOTALL | re.IGNORECASE)
    if xml_match:
        return xml_match.group(1).strip(), xml_match.group(2).strip()
    
    # Phase 55: Fallback XML for models that might omit the brackets inside the tag
    xml_bare_match = re.search(r"<action>\s*(.*?)\s*</action>", response_text, re.DOTALL | re.IGNORECASE)
    if xml_bare_match:
        raw_inner = xml_bare_match.group(1).strip()
        parts = raw_inner.split(None, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    # 2. Try JSON parsing
    try:
        # Look for non-greedy JSON block anywhere in the text
        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if not json_match:
            # Fallback for complex JSON
            json_match = re.search(r"\{.*?\}", response_text, re.DOTALL)
            
        if json_match:
            data = json.loads(json_match.group(0))
            action = data.get("action")
            payload = data.get("content") or data.get("goal") or data.get("payload")
            if action and payload:
                return str(action), str(payload)
    except Exception:
        pass

    # 3. Traditional & Fuzzy ReAct parsing
    # Supports "Action:", "Route to:", "Task:", "Call:", "Delegate to:"
    # Phase 2.7.3: Unified ReAct & Function-Call parsing
    header_regex = r"(?:Action|Route to|Task|Call|Delegate to):\s*([a-zA-Z0-9_\-]+)"
    header_match = re.search(header_regex, response_text, re.IGNORECASE)
    
    # 3.5: If no header match, look for bare tool calls that occur after a Thought: prefix
    # or just tool-like calls on their own line (common in Gemini/OpenRouter)
    if not header_match:
        # First, try to find a tool call like hybrid_search(query="...")
        # (This is aggressive but necessary for 'reasoning-chat' models on OpenRouter)
        tool_call_match = re.search(r"^\s*([a-zA-Z0-9_\-]+)\s*[\(\{\[](.*?)[\)\}\]]\s*$", response_text, re.MULTILINE | re.DOTALL)
        if not tool_call_match:
            # Look for it anywhere in the text if it's the ONLY thing that looks like a call
            tool_call_match = re.search(r"([a-zA-Z0-9_\-]+)\s*\((.*?)\)", response_text, re.IGNORECASE)
        
        if tool_call_match:
            action_type = tool_call_match.group(1).strip()
            payload = tool_call_match.group(2).strip()
            
            # If we match something that looks like an observation, or a word that isn't a tool, skip it
            # (Phase 2.7.3 Hardening)
            # Phase 3.7: Synchronized tool registry whitelist
            KNOWN_TOOLS = (
                "hybrid_search", "web_search", "web_scrape", "read_file", "list_dir", 
                "write_file", "run_command", "complete", "respond", 
                "capability", "code", "research", "executor", "memory", "email_agent"
            )
            if action_type.lower() not in [t.lower() for t in KNOWN_TOOLS]:
                return None
                
            # Strip common argument keys (query=, task=, etc.)
            for p in ["query=", "task=", "goal=", "path=", "cmd=", "url=", "message=", "summary="]:
                if payload.lower().startswith(p):
                    payload = payload[len(p):].strip()
                    break
            
            # Phase 3.7: Aggressive quote stripping for bare calls
            if len(payload) >= 2 and payload[0] in ['"', "'"] and payload[-1] == payload[0]:
                payload = payload[1:-1].strip()

            return action_type, payload
            
        # 3.7 Phase 11 Fallback: Regex for 'Final Answer' or 'answer='
        # Check this BEFORE giving up and returning None
        fb_match = re.search(r"(?:Final Answer:|answer=)\s*[:\"']*(.*?)(?:[\"']|$)", response_text, re.IGNORECASE | re.DOTALL)
        if fb_match:
            return "respond", fb_match.group(1).strip()

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
    
    # 4. Cleanup: Strip common prefixes like message="..." or content="..."
    prefixes = ['message=', 'content=', 'payload=', 'goal=', 'task=', 'query=', 'command=', 'summary=']
    for prefix in prefixes:
        if payload.lower().startswith(prefix):
            payload = payload[len(prefix):].strip()
            break
            
    # 4.5 Stripping surrounding quotes from the final payload
    # Handles ('path'), ("path"), [path], etc. 
    # Must be done AFTER prefix stripping.
    if len(payload) >= 2:
        if (payload[0] == '"' and payload[-1] == '"') or \
           (payload[0] == "'" and payload[-1] == "'") or \
           (payload[0] == "(" and payload[-1] == ")") or \
           (payload[0] == "[" and payload[-1] == "]") or \
           (payload[0] == "{" and payload[-1] == "}"):
            payload = payload[1:-1].strip()

    return action_type, payload

def parse_thought(response_text: str) -> str:
    """
    Extracts the reasoning thought from the response.
    Harden: Capture as a 'thought' if a valid specialist/action block follows it.
    """
    headers = ["Action:", "Route to:", "Task:", "Call:", "Delegate to:", "<action"]
    h_lookahead = "|".join(headers)
    match = re.search(rf"Thought:\s*(.*?)(?=\n(?:{h_lookahead}))", response_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

def _strip_react_internals(text: str) -> str:
    """Remove Thought:/Action: and <|thinking|> blocks from LLM output."""
    cleaned = strip_all_reasoning(text)
    return cleaned or text

def strip_all_reasoning(text: str) -> str:
    """
    Aggressively strips all forms of reasoning from a string.
    Handles:
    - <|thinking|>...</|thinking|>
    - Thought: ... (until Action: or end of string)
    - Early chatter that doesn't look like an action.
    """
    if not text:
        return ""
        
    # 1. Strip all XML-style and bracket-style thinking tags (complete blocks)
    # Supports <thinking>, <|thinking|>, [thought], etc. and their corresponding ends.
    tag_patterns = [
        r"<\|thinking\|>.*?</\|thinking\|>",
        r"<thinking>.*?</thinking>",
        r"\[thought\].*?\[/thought\]"
    ]
    for pattern in tag_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1.5 Strip dangling or unclosed tags (catch hallucinations)
    # Supports mixtures where start/end tags don't perfectly match (common in Quantized models)
    dangling_patterns = [
        r"<\|?thinking\|?>",
        r"</\|?thinking\|?>",
        r"\[/?thought\]"
    ]
    for pattern in dangling_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    # 2. Strip Thinking/Thought blocks followed by Action
    # Supports all known headers: Action, Route to, Task, Call, Delegate to, <action
    text = re.sub(r"(?:Thought|Thinking):\s*.*?(?=\n?\s*<action|Action:|Route to:|Task:|Call:|Delegate to:)", "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Strip dangling "Thought:" or "Thinking:" prefixes
    text = re.sub(r"^(?:Thought|Thinking):\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 4. Remove any action tags themselves if they are at the end
    text = re.sub(r"<action>.*?</action>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Correctness: Remove re.DOTALL for bare Action: strip to avoid over-stripping payload
    text = re.sub(r"Action:\s*.*", "", text, flags=re.IGNORECASE)
    
    # 5. Clean up "Final Answer:" prefixes if they leaked through
    text = re.sub(r"^Final Answer:\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()
