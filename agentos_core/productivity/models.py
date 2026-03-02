"""
Models for Personal Productivity features.
"""

from enum import Enum
from typing import Optional, List, Dict, Union
from datetime import datetime
from pydantic import BaseModel, Field


class TodoStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoItem(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    priority: Union[int, str] = 1  # 1-5 or "low", "medium", "high"
    due_date: Optional[Union[datetime, str]] = None
    status: TodoStatus = TodoStatus.PENDING
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class Note(BaseModel):
    id: str
    title: str
    content: str
    source: Optional[str] = None  # file path, URL, etc.
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class Briefing(BaseModel):
    date: datetime
    weather_summary: Optional[str] = None
    todos_due: List[TodoItem] = Field(default_factory=list)
    calendar_events: List[dict] = Field(default_factory=list)
    news_summary: Optional[str] = None


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PlanStep(BaseModel):
    action: str
    tool_name: Optional[str] = None
    args: Dict[str, str] = Field(default_factory=dict)
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: Optional[str] = None


class TaskPlan(BaseModel):
    id: str
    goal: str
    steps: List[PlanStep]
    status: str = "created"
    context: Dict[str, str] = Field(default_factory=dict)
