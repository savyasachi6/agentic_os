"""
agents/worker.py
=================
Base class for Specialist Agent Workers that consume commands from a lane.
"""

import threading
import time
import traceback
import asyncio
import json
from typing import Optional, Any
from db.queries.commands import TreeStore
from agent_core.types import NodeStatus, AgentRole

class AgentWorker:
    """
    Poller that pulls tasks from a TreeStore (Execution Tree) and executes them using a Specialist Agent.
    """
    def __init__(self, role: AgentRole, agent: Any, store: TreeStore, poll_interval: float = 1.0):
        self.role = role
        self.agent = agent
        self.tree_store = store
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name=f"worker-{self.role.value}", daemon=True)
        self._thread.start()
        print(f"[AgentWorker] Started worker for role: {self.role.value}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        print(f"[AgentWorker] Stopped worker for role: {self.role.value}")

    def _loop(self):
        # Create a local event loop for this thread's async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while not self._stop_event.is_set():
            try:
                # Dequeue from TreeStore nodes table
                task = loop.run_until_complete(self.tree_store.dequeue_task_async(self.role))
                if task is None:
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue

                print(f"[AgentWorker] Processing Task {task.id} for {self.role.value}")
                
                try:
                    # Execute agent logic (support both task object and query string)
                    if hasattr(self.agent, "_process_task"):
                        loop.run_until_complete(self.agent._process_task(task))
                    else:
                        query = task.payload.get("query", task.payload.get("task", task.content))
                        result = self.agent.execute(query)
                        loop.run_until_complete(self.tree_store.update_node_status_async(task.id, NodeStatus.DONE, result={"content": result}))
                    
                    print(f"[AgentWorker] ✓ Completed Task {task.id}")
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    loop.run_until_complete(self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": error_msg}))
                    print(f"[AgentWorker] ✗ Failed Task {task.id}: {error_msg}")
                    traceback.print_exc()

            except Exception as e:
                print(f"[AgentWorker] Global error in {self.role.value} loop: {e}")
                time.sleep(self.poll_interval)
        loop.close()
