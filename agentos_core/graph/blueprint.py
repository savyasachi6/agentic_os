"""
agent_core/graph/blueprint.py (SHIM)
====================================
Shim for backward compatibility.
Logic moved to: core/graph/blueprint.py
"""
from core.graph.blueprint import create_agent_os_kernel, compile_durable_graph

__all__ = ["create_agent_os_kernel", "compile_durable_graph"]
