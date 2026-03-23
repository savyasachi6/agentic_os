"""
agent_core/llm.py (COMPATIBILITY SHIM)
======================================
This file exists for backward compatibility during the architecture refactor.
The LLMClient logic has been moved to: llm/client.py

Do not add new methods here. Import from llm.client directly.
"""
from llm.client import LLMClient, get_llm, generate_structured_output

__all__ = ["LLMClient", "get_llm", "generate_structured_output"]
