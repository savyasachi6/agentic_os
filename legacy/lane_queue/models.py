"""
Lane Queue models: enums and Pydantic schemas for lanes and commands.
"""

from enum import Enum
from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class CommandStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommandType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    HUMAN_REVIEW = "human_review"


class RiskLevel(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Lane(BaseModel):
    id: str
    session_id: str
    name: str = "default"
    risk_level: RiskLevel = RiskLevel.NORMAL
    is_active: bool = True
    created_at: Optional[datetime] = None


class Command(BaseModel):
    id: str
    lane_id: str
    seq: int
    status: CommandStatus = CommandStatus.PENDING
    cmd_type: CommandType
    tool_name: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    sandbox_id: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
