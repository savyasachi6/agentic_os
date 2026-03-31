from typing import Any

def extract_text(content: Any) -> str:
    """
    Stabilization FIX (B1): Safely extract a string representation from message content.
    Handles:
    - String literals
    - List of multi-modal content blocks (OpenAI/LangChain format)
    - Node/Message objects with a 'content' attribute
    """
    if content is None:
        return ""
    
    # Handle direct string cases
    if isinstance(content, str):
        return content
        
    # Handle LangChain message objects with .content attribute
    if hasattr(content, "content"):
        return extract_text(content.content)

    # Handle multi-modal content lists:
    # [{"type": "text", "text": "foo"}, {"type": "image_url", ...}]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return " ".join(filter(None, parts)).strip()

    # Fallback to string representation for anything else (ints, basic dicts, etc.)
    return str(content)
