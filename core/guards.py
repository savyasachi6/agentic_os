"""
core/guards.py
==============
Input validation and type guard utilities.
Used at every agent and tool entry point to prevent
crashes from non-string inputs, None values, and
callable objects being passed as messages.
"""
from __future__ import annotations
import logging
import re
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)

def safe_str(value: Any, context: str = "") -> str:
    """Convert any value to a safe string for processing."""
    if value is None:
        logger.debug("safe_str received None%s, returning empty string", 
                     f" in {context}" if context else "")
        return ""
    if callable(value):
        logger.warning("safe_str received callable%s, using __name__",
                       f" in {context}" if context else "")
        return value.__name__
    if not isinstance(value, str):
        logger.debug("safe_str converting %s to str%s", type(value).__name__,
                     f" in {context}" if context else "")
        return str(value).strip()
    return value.strip()

def safe_dict(value: Any, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely get a dict, returning default if None or wrong type."""
    if isinstance(value, dict):
        return value
    return default or {}

def safe_list(value: Any, default: Optional[List[Any]] = None) -> List[Any]:
    """Safely get a list, returning default if None or wrong type."""
    if isinstance(value, list):
        return value
    return default or []

def safe_get(d: Any, key: str, default: Any = None) -> Any:
    """Safe dict key access that never raises KeyError."""
    return safe_dict(d).get(key, default)

def is_safe_command(command: str) -> bool:
    """Check if a shell command is safe to execute."""
    prohibited = [
        r"rm\s+-rf\s+/", r"mkfs", r"dd\s+if=", r"shutdown", r"reboot",
        r"chmod\s+777", r"chown", r">", r">>", r"\|", r";", r"&&"
    ]
    for pattern in prohibited:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    return True

class AgentCallGuard:
    """
    Prevents agent loops. Hard stops after limits.
    Every coordinator turn creates a fresh guard instance.
    """
    def __init__(self, max_per_agent: int = 2, max_total: int = 8):
        self.max_per_agent = max_per_agent
        self.max_total = max_total
        self._counts: Dict[str, int] = {}
        self._total: int = 0
        self._call_log: List[Dict[str, Any]] = []

    def can_call(self, agent_name: str) -> bool:
        if self._total >= self.max_total:
            return False
        return self._counts.get(agent_name, 0) < self.max_per_agent

    def record(self, agent_name: str, payload: str = ""):
        self._counts[agent_name] = self._counts.get(agent_name, 0) + 1
        self._total += 1
        import time
        self._call_log.append({
            "agent": agent_name,
            "call_number": self._counts[agent_name],
            "total": self._total,
            "timestamp": time.time(),
            "payload_preview": payload[:80]
        })

    def exhausted(self) -> bool:
        return self._total >= self.max_total

    def get_log(self) -> List[Dict[str, Any]]:
        return self._call_log

    def summary(self) -> str:
        return f"Total calls: {self._total}/{self.max_total} | " + \
               " | ".join(f"{k}:{v}" for k, v in self._counts.items())
