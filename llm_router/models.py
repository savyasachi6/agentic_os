from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class LLMRequest(BaseModel):
    request_id: str
    session_id: str
    messages: List[Dict[str, str]]
    model: str
    max_tokens: int = 2048
    temperature: float = 0.7
    
class LLMResponse(BaseModel):
    request_id: str
    session_id: str
    content: str
    error: Optional[str] = None
    
class BatchGroup(BaseModel):
    model: str
    max_tokens: int
    requests: List[LLMRequest] = Field(default_factory=list)
