"""
agents/productivity.py
======================
Refactored ProductivityAgentWorker using modular imports.
Handles background maintenance for todos and notes.
"""
import asyncio
import logging
from productivity.todo_manager import TodoManager
from productivity.notes import NoteManager
from agent_core.agents.core.a2a_bus import A2ABus

logger = logging.getLogger("agentos.agents.productivity")

class ProductivityAgent:
    """
    Background worker for productivity maintenance (todos/notes).
    """
    def __init__(self):
        self.todo_manager = TodoManager()
        self.note_manager = NoteManager(None) # Assuming None is acceptable for now
        self.bus = A2ABus()
        self.stop_event = asyncio.Event()

    async def run_forever(self, poll_interval: float = 60.0):
        print("[ProductivityAgent] Worker started.")
        while not self.stop_event.is_set():
            try:
                # Background maintenance
                await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("ProductivityAgent error: %s", e)
                await asyncio.sleep(poll_interval)
