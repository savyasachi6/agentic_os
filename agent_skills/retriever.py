"""
agent_skills/retriever.py (SHIM)
================================
Shim for backward compatibility.
Logic moved to: rag/retriever.py
"""
from rag.retriever import HybridRetriever as SkillRetriever

__all__ = ["SkillRetriever"]
