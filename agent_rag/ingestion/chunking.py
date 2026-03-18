# src/ingestion/chunking.py
from typing import List, Dict, Any

def chunk_structured_doc(structured_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Structure-aware chunking.
    Prioritizes keeping paragraphs under their parent heading, and never slicing tables.
    """
    chunks = []
    current_heading = None
    current_content = []
    current_tokens = 0
    MAX_TOKENS = 512 # Soft limit

    for element in structured_elements:
        if element["type"] in ["Title", "Heading"]:
            # If we already have content under a different heading, save the chunk
            if current_content:
                chunks.append({
                    "heading": current_heading,
                    "content": "\n".join(current_content)
                })
                current_content = []
                current_tokens = 0
            current_heading = element["text"]
            
        elif element["type"] == "Table":
            # Tables are treated as sacred and chunked immediately to avoid cross-boundary slicing
            if current_content:
                chunks.append({
                    "heading": current_heading,
                    "content": "\n".join(current_content)
                })
                current_content = []
                current_tokens = 0
            chunks.append({
                "heading": current_heading,
                "content": element["text"]
            })
            
        else: # Paragraph, List Item
            # Rough approximation of tokens (words * 1.3)
            estimated_tokens = len(element["text"].split()) * 1.3
            if current_tokens + estimated_tokens > MAX_TOKENS and current_content:
                chunks.append({
                    "heading": current_heading,
                    "content": "\n".join(current_content)
                })
                current_content = []
                current_tokens = 0
                
            current_content.append(element["text"])
            current_tokens += estimated_tokens

    # Flush remaining
    if current_content:
        chunks.append({
            "heading": current_heading,
            "content": "\n".join(current_content)
        })

    return chunks
