"""
Models for DevOps automation.
"""

from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class DevOpsTestRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class DevOpsTestRun(BaseModel):
    id: str
    cmd: str
    cwd: str
    status: DevOpsTestRunStatus = DevOpsTestRunStatus.PENDING
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0


class DeploymentState(str, Enum):
    DEPLOYING = "deploying"
    LIVE = "live"
    ROLLING_BACK = "rolling_back"
    FAILED = "failed"


class DeploymentConfig(BaseModel):
    target: str  # "staging" or "prod"
    image_tag: str
    rollback_to: Optional[str] = None
    env_vars: Dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True


class AlertRule(BaseModel):
    metric_name: str
    threshold: float
    comparison: str  # ">", "<", ">=", "<=", "=="
    action: str  # "page" or "warn"


class PRSpec(BaseModel):
    branch_name: str
    title: str
    body: str
    file_changes: List[str]


class ChatMessage(BaseModel):
    platform: str  # "telegram" or "slack"
    user_id: str
    text: str
    channel: str
