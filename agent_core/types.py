"""
core/types.py
=============
Central type definitions for agentic_os.
All shared enums, dataclasses, and TypedDicts live here.
No business logic. No imports from other agentic_os modules.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

class Intent(Enum):
    CAPABILITY_QUERY = "capability_query"
    RAG_LOOKUP       = "rag_lookup"
    WEB_SEARCH       = "web_search"
    EXECUTION        = "execution"
    FILESYSTEM       = "filesystem"
    CODE_GEN         = "code_gen"
    MEMORY_QUERY     = "memory_query"
    LLM_DIRECT       = "llm_direct"
    SIMPLE_TASK      = "simple_task"
    COMPLEX_TASK     = "complex_task"
    STATUS_QUERY     = "status_query"
    GREETING         = "greeting"

class RiskLevel(str, Enum):
    LOW    = "low"
    NORMAL = "normal"
    HIGH   = "high"

class AgentRole(str, Enum):
    RAG = "rag"
    SCHEMA = "schema"
    TOOLS = "tools"
    ORCHESTRATOR = "orchestrator"
    EMAIL = "email"
    PLANNER = "planner"
    PRODUCTIVITY = "productivity"
    SPECIALIST = "specialist"

class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

class NodeType(str, Enum):
    PLAN = "plan"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RESULT = "result"
    SUMMARY = "summary"
    TASK = "task"

@dataclass
class AgentResult:
    success: bool
    content: str
    agent: str
    intent: Optional[Intent] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

@dataclass
class ToolCall:
    tool_name: str
    parameters: Dict[str, Any]
    risk_level: RiskLevel = RiskLevel.NORMAL
    result: Optional[Any] = None
    error: Optional[str] = None
