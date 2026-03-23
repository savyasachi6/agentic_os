"""
agent_core/agents/universal_agent.py (SHIM)
==========================================
Shim for backward compatibility.
Logic moved to: agents/executor.py
"""
from agents.executor import ExecutorAgentWorker as UniversalAgentWorker

__all__ = ["UniversalAgentWorker"]
