"""
agent_core/agents/sql_agent.py (SHIM)
=====================================
Shim for backward compatibility.
Logic moved to: agents/capability_agent.py
"""
from agents.capability_agent import CapabilityAgentWorker as SQLAgentWorker

__all__ = ["SQLAgentWorker"]
