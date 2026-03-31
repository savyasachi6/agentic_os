import re as _re
from typing import Optional

def normalize_thought(thought_text: Optional[str]) -> str:
    """
    Robustly clean model turn markers and normalize whitespace.
    Handles [Turn X/Y], **[Turn X/Y]**, Thought: [Turn 1/4], etc.
    Also strips internal verbatim repetitions.
    """
    if not thought_text:
        return ""
    
    # 1. Multi-pass turn marker stripping
    text = _re.sub(r"(?im)^\s*(?:\*\*)?\[?\s*(?:turn|iteration|step)\s+\d+\s*/\s*\d+\s*\]?(?:\*\*)?:?\s*", "", thought_text)
    text = _re.sub(r"(?i)(?:\*\*)?\[?\s*(?:turn|iteration|step)\s+\d+\s*/\s*\d+\s*\]?(?:\*\*)?:?\s*", "", text)

    # 2. Duplicate detection (strips verbatim repetitions within the same thought)
    # This handles models repeating the same sentence or turn marker again.
    text = text.strip()
    mid = len(text) // 2
    if len(text) > 20 and text[:mid].strip() == text[mid:].strip():
        text = text[:mid].strip()

    # 3. Collapse multiple newlines and spaces
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = _re.sub(r"[ \t]{2,}", " ", text)
    
    return text.strip()

def should_publish(new_thought: str, last_thought: Optional[str]) -> bool:
    """
    Determines if a thought is substantively different from the last published one.
    Normalizes both sides before comparison to ignore whitespace changes.
    """
    if not new_thought:
        return False
        
    normalized_new = normalize_thought(new_thought)
    if not normalized_new:
        return False
        
    if not last_thought:
        return True
        
    normalized_last = normalize_thought(last_thought)
    return normalized_new != normalized_last
