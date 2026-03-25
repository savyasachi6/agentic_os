"""
agents/worker.py
=================
Base class for Specialist Agent Workers that consume commands from a lane.
"""

import threading
import time
import traceback
from typing import Optional, Any
from lane_queue.store import CommandStore
from lane_queue.models import CommandStatus

class AgentWorker:
    """
    Poller that pulls tasks from a TreeStore (Lane Queue) and executes them using a Specialist Agent.
    """
    def __init__(self, role: str, agent: Any, store: CommandStore, poll_interval: float = 1.0):
        self.role = role
        self.agent = agent
        self.store = store
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name=f"worker-{self.role}", daemon=True)
        self._thread.start()
        print(f"[AgentWorker] Started worker for role: {self.role}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        print(f"[AgentWorker] Stopped worker for role: {self.role}")

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                # Find an active lane for this role
                # In this simplified model, we assume a one-to-one mapping for now or use a global queue
                # For now, let's assume we poll a "global" lane named after the role
                cmd = self.store.claim_next(self.role) 
                if cmd is None:
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue

                print(f"[AgentWorker] Processing {cmd.cmd_type} (seq={cmd.seq}) for {self.role}")
                
                # Execute agent logic
                try:
                    # Payload is the query or task
                    query = cmd.payload.get("query", cmd.payload.get("task", ""))
                    result = self.agent.execute(query) # Specialist agents should have an .execute() or .run_turn()
                    
                    self.store.complete(cmd.id, {"content": result})
                    print(f"[AgentWorker] ✓ Completed {cmd.id}")
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.store.fail(cmd.id, error_msg)
                    print(f"[AgentWorker] ✗ Failed {cmd.id}: {error_msg}")
                    traceback.print_exc()

            except Exception as e:
                print(f"[AgentWorker] Global error in {self.role} loop: {e}")
                time.sleep(self.poll_interval)
