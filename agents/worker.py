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
from core.agent_types import NodeStatus, AgentRole

class AgentWorker:
    """
    Poller that pulls tasks from a TreeStore (Execution Tree) and executes them using a Specialist Agent.
    """
    def __init__(self, role: AgentRole, agent: Any, store: TreeStore, poll_interval: float = 1.0):
        from core.message_bus import A2ABus
        self.role = role
        self.agent = agent
        self.tree_store = store
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dispatch_queue: Optional[asyncio.Queue] = None
        
        # Ensure agent has a bus if not provided (Phase 5 Hardening)
        if not hasattr(self.agent, "bus") or not self.agent.bus:
            self.agent.bus = A2ABus()

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
            # Wake up the queue if it's waiting
            if self._dispatch_queue:
                # We can't easily put from here because it's in a different thread
                # but the stop_event check in the loop will handle it.
                pass
            self._thread.join(timeout=10)
        print(f"[AgentWorker] Stopped worker for role: {self.role.value}")

    async def _heartbeat_loop(self):
        """Background task to keep heartbeat alive (Phase 5 Hardening)."""
        while not self._stop_event.is_set():
            try:
                if hasattr(self.agent, "bus") and self.agent.bus:
                    await self.agent.bus.set_heartbeat(self.role.value)
            except Exception as e:
                print(f"[AgentWorker] Heartbeat error: {e}")
            await asyncio.sleep(15) # Pulse every 15s (TTL is 30s)

    async def _listen_loop(self):
        """Listens for immediate dispatch messages from the A2A Bus."""
        if not hasattr(self.agent, "bus") or not self.agent.bus:
            from core.message_bus import A2ABus
            self.agent.bus = A2ABus()
            
        print(f"[AgentWorker] Listening for immediate dispatch on: {self.role.value}")
        async for msg in self.agent.bus.listen(self.role.value):
            if self._stop_event.is_set():
                break
            
            node_id = msg.get("node_id")
            if node_id and self._dispatch_queue:
                await self._dispatch_queue.put(node_id)

    async def _task_loop(self):
        """Main task loop for dequeuing and processing."""
        self._dispatch_queue = asyncio.Queue()
        
        while not self._stop_event.is_set():
            try:
                # 1. Wait for an immediate dispatch ID, or timeout to poll
                target_node_id = None
                try:
                    # Wait for a message with a timeout (equivalent to poll interval)
                    target_node_id = await asyncio.wait_for(
                        self._dispatch_queue.get(), 
                        timeout=self.poll_interval
                    )
                except asyncio.TimeoutError:
                    # Normal polling timeout
                    target_node_id = None

                # 2. Dequeue from TreeStore (either specific ID or next available)
                task = await self.tree_store.dequeue_task_async(self.role, node_id=target_node_id)
                
                if task is None:
                    # If we had a target_node_id but it vanished (claimed by someone else), 
                    # we should probably do a quick poll anyway.
                    if target_node_id:
                        task = await self.tree_store.dequeue_task_async(self.role)
                    
                    if task is None:
                        continue

                from datetime import datetime
                ts = datetime.now().isoformat()
                print(f"[{ts}] [AgentWorker] Processing Task {task.id} for {self.role.value} (Dispatch: {target_node_id is not None})")
                
                try:
                    # Use polymorphic entry point (run, _process_task, or handle_task)
                    # Phase 48: Capture results to ensure NodeStatus.DONE is pushed automatically.
                    result = None
                    if hasattr(self.agent, "run"):
                        await self.agent.run(task)
                    elif hasattr(self.agent, "_process_task"):
                        result = await self.agent._process_task(task)
                    elif hasattr(self.agent, "handle_task"):
                        result = await self.agent.handle_task(task)
                    else:
                        # Fallback to old execute method if no specific handler is found
                        query = task.payload.get("query", task.payload.get("task", task.content))
                        result = self.agent.execute(query)
                    
                    # If Agent didn't manually close the node but returned a result, close it now.
                    # This prevents "stuck" intent classification.
                    if result is not None:
                        # Extract content if result is a dict with 'response' or 'content'
                        content = result
                        if isinstance(result, dict):
                            content = result.get("response", result.get("content", result))
                        
                        await self.tree_store.update_node_status_async(
                            task.id, 
                            NodeStatus.DONE, 
                            result={"content": content, "details": result if isinstance(result, dict) else None}
                        )
                    
                    ts_done = datetime.now().isoformat()
                    print(f"[{ts_done}] [AgentWorker] ✓ Completed Task {task.id}")
                    
                    # Notify subscribers via A2A Bus (Phase 5 Hardening)
                    if hasattr(self.agent, "bus") and self.agent.bus:
                        await self.agent.bus.publish(f"node_done:{task.id}", {"status": "DONE"})
                        
                except Exception as e:
                    ts_fail = datetime.now().isoformat()
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    await self.tree_store.update_node_status_async(task.id, NodeStatus.FAILED, result={"error": error_msg})
                    print(f"[{ts_fail}] [AgentWorker] ✗ Failed Task {task.id}: {error_msg}")
                    
                    # Notify failure via A2A Bus (Phase 5 Hardening)
                    if hasattr(self.agent, "bus") and self.agent.bus:
                        await self.agent.bus.publish(f"node_done:{task.id}", {"status": "FAILED", "error": error_msg})
                    
                    traceback.print_exc()

            except Exception as e:
                print(f"[AgentWorker] Task loop error in {self.role.value}: {e}")
                await asyncio.sleep(self.poll_interval)

    def _loop(self):
        # Create a local event loop for this thread's async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run heartbeat, listener, and task loop concurrently
            loop.run_until_complete(asyncio.gather(
                self._heartbeat_loop(),
                self._listen_loop(),
                self._task_loop()
            ))
        except Exception as e:
            if not self._stop_event.is_set():
                print(f"[AgentWorker] Global loop crash in {self.role.value}: {e}")
        finally:
            loop.close()

