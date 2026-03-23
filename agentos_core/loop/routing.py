"""
agent_core/loop/routing.py (SHIM)
=================================
Shim for backward compatibility.
Logic moved to: intent/routing.py
"""
from intent.routing import route_action_to_agent

__all__ = ["route_action_to_agent"]
