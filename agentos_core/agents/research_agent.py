"""
agent_core/agents/research_agent.py (SHIM)
==========================================
Shim for backward compatibility.
Logic moved to: agents/rag_agent.py
"""
from agents.rag_agent import RAGAgentWorker as ResearcherAgentWorker

__all__ = ["ResearcherAgentWorker"]
