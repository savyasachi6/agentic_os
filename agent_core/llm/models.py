from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import IntEnum, Enum

class ModelTier(str, Enum):
    NANO = "nano"    # ≤1GB — rewrites, intent checks, summaries
    FAST = "fast"    # ≤4GB — short RAG, single-turn responses
    FULL = "full"    # ≤6GB — coordinator, code gen, complex reasoning

class Priority(IntEnum):
    OBSERVER = 1        # Highest priority (e.g. real-time thought)
    NORMAL = 2          # Standard requests
    SUMMARIZATION = 3   # Lower priority (background tasks)

class LLMRequest(BaseModel):
    request_id: str
    session_id: str
    messages: List[Dict[str, str]]
    model: str
    max_tokens: int = 2048
    temperature: float = 0.7
    priority: Priority = Priority.NORMAL
    stop: Optional[List[str]] = None
    
class LLMResponse(BaseModel):
    request_id: str
    session_id: str
    content: str
    error: Optional[str] = None
    
class BatchGroup(BaseModel):
    model: str
    max_tokens: int
    requests: List[LLMRequest] = Field(default_factory=list)
