"""
agent_core/loop/thought_loop.py (SHIM)
=====================================
Shim for backward compatibility.
Logic moved to: core/reasoning.py
"""
from core.reasoning import parse_react_action, parse_thought

__all__ = ["parse_react_action", "parse_thought"]
