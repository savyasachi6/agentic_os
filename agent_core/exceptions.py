"""
core/exceptions.py
==================
All custom exception classes for agentic_os.
Import from here, never define exceptions inline in agent files.
"""

class AgenticOSError(Exception):
    """Base exception for all agentic_os errors."""

class IntentClassificationError(AgenticOSError):
    """Raised when intent cannot be classified."""

class AgentRoutingError(AgenticOSError):
    """Raised when no agent can handle the given intent."""

class ToolExecutionError(AgenticOSError):
    """Raised when a tool fails to execute."""

class DatabaseError(AgenticOSError):
    """Raised for database operation failures."""

class ForeignKeyError(DatabaseError):
    """Raised when FK constraint would be violated."""

class LLMError(AgenticOSError):
    """Raised when LLM call fails or returns invalid output."""

class ReasoningBudgetExceeded(AgenticOSError):
    """Raised when per-message agent call limit is exceeded."""

class WebSearchUnavailable(AgenticOSError):
    """Raised when Lightpanda or web search cannot be reached."""
