"""
Sandbox models: configuration and runtime state for sandboxed tool workers.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class WorkerStatus(str, Enum):
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    STOPPING = "stopping"
    DEAD = "dead"


class SandboxConfig(BaseModel):
    """Resource limits and allowed tools for a sandbox worker."""
    timeout_seconds: int = 300
    max_memory_mb: int = 512
    allowed_tools: Optional[List[str]] = None   # None = all tools allowed
    env_vars: dict = Field(default_factory=dict)


class SandboxInfo(BaseModel):
    """Runtime state of a sandbox worker process."""
    sandbox_id: str
    session_id: str
    pid: Optional[int] = None
    port: int
    status: WorkerStatus = WorkerStatus.STARTING
    base_url: str = ""
    config: SandboxConfig = Field(default_factory=SandboxConfig)

    def model_post_init(self, __context):
        if not self.base_url:
            self.base_url = f"http://127.0.0.1:{self.port}"


class ToolRequest(BaseModel):
    """Wire format: runner → worker."""
    tool_name: str
    args: dict = Field(default_factory=dict)
    timeout_seconds: Optional[int] = None


class ToolResponse(BaseModel):
    """Wire format: worker → runner."""
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


# ── Per-tool call wire models (used by worker.py endpoints) ──────────

from typing import Dict, Any  # noqa: E402  (already imported above in practice)


class ToolCallRequest(BaseModel):
    """
    Request body for POST /tools/{tool_name}.
    Fields are kept intentionally loose so a single model works for all tools.
    """
    command: Optional[str] = None
    cwd: Optional[str] = None
    timeout_seconds: int = 300
    content: Optional[str] = None
    path: Optional[str] = None
    query: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """Response body from POST /tools/{tool_name}."""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
