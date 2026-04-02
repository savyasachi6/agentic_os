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
    Uses Jaccard Token Similarity to suppress near-duplicates (threshold 0.8).
    """
    if not new_thought:
        return False
        
    normalized_new = normalize_thought(new_thought)
    if not normalized_new:
        return False
        
    if not last_thought:
        return True
        
    normalized_last = normalize_thought(last_thought)
    if normalized_new == normalized_last:
        return False

    # Jaccard Token Similarity (Phase 105 Optimization)
    def get_tokens(t: str): return set(t.lower().split())
    
    tokens_new = get_tokens(normalized_new)
    tokens_last = get_tokens(normalized_last)
    
    if not tokens_new or not tokens_last:
        return True
        
    intersection = tokens_new.intersection(tokens_last)
    union = tokens_new.union(tokens_last)
    similarity = len(intersection) / len(union)
    
    # If 80% of words are the same, treat as duplicate
    return similarity < 0.8

def get_thought_delta(new_thought: str, last_thought: Optional[str]) -> str:
    """
    Extracts the incremental delta from a potentially cumulative thought block.
    If the new thought is a superset of the last one, it returns only the tail.
    Otherwise, returns the normalized new thought.
    """
    if not new_thought:
        return ""
    
    n_new = normalize_thought(new_thought)
    if not last_thought:
        return n_new
        
    n_last = normalize_thought(last_thought)
    
    # Simple prefix removal if the model is repeating previous turns
    if n_new.startswith(n_last):
        delta = n_new[len(n_last):].strip()
        # Clean up any leading punctuation or conjunctions that look messy
        delta = _re.sub(r"^[ \t\n,.:;]+", "", delta)
        return delta
        
    # If not a prefix but still highly similar, it's likely a mutation — 
    # treat as non-delta to avoid showing near-identical sentences.
    if not should_publish(n_new, n_last):
        return ""
        
    return n_new
