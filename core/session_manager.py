# core/session_manager.py
import uuid
import time
from typing import Dict, Any, Optional
from db.commands import log_event
from db.connection import get_redis
from .guard import AgentCallGuard

class SessionManager:
    """
    Handles session lifecycle, state persistence, and event logging.
    Injects memory context and manages the AgentCallGuard per turn.
    """
    def __init__(self):
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    async def create_session(self, session_id: Optional[str] = None) -> str:
        s_id = session_id or str(uuid.uuid4())
        if s_id not in self._active_sessions:
            self._active_sessions[s_id] = {
                "created_at": time.time(),
                "last_active": time.time(),
                "metadata": {}
            }
            await log_event(s_id, "session_start", {"session_id": s_id})
        return s_id

    async def get_guard(self, max_per_agent: int = 2, max_total: int = 8) -> AgentCallGuard:
        """Create a fresh guard for a new coordinator turn."""
        return AgentCallGuard(max_per_agent=max_per_agent, max_total=max_total)

    async def log_activity(self, session_id: str, activity_type: str, data: Dict[str, Any]):
        if session_id in self._active_sessions:
            self._active_sessions[session_id]["last_active"] = time.time()
        await log_event(session_id, activity_type, data)

    async def check_redis_status(self) -> bool:
        try:
            r = await get_redis()
            return await r.ping()
        except:
            return False

# Global session manager instance
session_manager = SessionManager()
