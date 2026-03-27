from pydantic import BaseModel, Field

class FileCategory(BaseModel):
    """
    Structured categorization of a file by the LLM.
    """
    category: str = Field(..., description="Target folder category (e.g. Images, Documents, Code, Archives)")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Brief explanation for the categorization")
