# Agent Roles and Workers

This document maps the logical agents in Agentic OS to their `AgentRole`, specialist files, and worker implementations.

## Agent Mapping

| AgentRole | Class | File | Description |
| :--- | :--- | :--- | :--- |
| `rag` | `ResearchAgentWorker` | `agent_core/agents/specialists/rag_agent.py` | Research, fact-checking, hybrid KB search, web search, and long-term memory retrieval. |
| `tools` | `CodeAgentWorker` | `agent_core/agents/specialists/code_agent.py` | Code execution and general systems tasks. |
| `schema` | `CapabilityAgentWorker` | `agent_core/agents/specialists/capability_agent.py` | Fast-path capability queries and skill discovery. |
| `email` | `EmailAgent` | `agent_core/agents/specialists/email_agent.py` | Email management and notifications. |
| `productivity` | `ProductivityAgent` | `agent_core/agents/specialists/productivity.py` | Calendar, tasks, and notes management. |
| `specialist` | `ExecutorAgentWorker` | `agent_core/agents/specialists/executor.py` | Generic specialized task execution. |
| `planner` | `PlannerAgentWorker` | `agent_core/agents/specialists/planner.py` | High-level strategy and breakdown of complex tasks. |

> **Note**: The `memory` intent in the coordinator aliases to the `rag` role — `memory` is **not** a separate worker process:
> ```python
> "memory": BridgeAgent(AgentRole.RAG, self.tree_store, self.bus)
> ```

---

## Routing & Dispatch

### Intent → Agent Mapping (coordinator.py)

The `CoordinatorAgent` maintains a registry keyed by logical name, not by `AgentRole`:

| Coordinator Key | `AgentRole` | Specialist |
|---|---|---|
| `research` | `RAG` | ResearchAgentWorker |
| `code` | `TOOLS` | CodeAgentWorker |
| `capability` | `SCHEMA` | CapabilityAgentWorker |
| `executor` | `SPECIALIST` | ExecutorAgentWorker |
| `planner` | `PLANNER` | PlannerAgentWorker |
| `productivity` | `PRODUCTIVITY` | ProductivityAgent |
| `email` | `EMAIL` | EmailAgent |
| `memory` | `RAG` | ResearchAgentWorker (same process) |

Intent classification (`agent_core/intent/classifier.py`) produces an `Intent` enum value which is stored in `AgentState`. The LangGraph routing nodes in `coordinator_graph.py` then map intents to the appropriate `BridgeAgent` key.

### BridgeAgent & Heartbeats

The `BridgeAgent` (defined inside `coordinator.py`) bridges the coordinator to background workers:

```python
# 1. Check heartbeat (fail-fast guard)
is_alive = await self.bus.get_heartbeat(self.role.value)
if not is_alive:
    return {"error_type": "offline", "error": "Specialist agent is offline."}

# 2. Create Node in TreeStore
task_node = await self.tree_store.add_node_async(node)

# 3. Publish to A2A Bus
await self.bus.send(self.role.value, {"node_id": task_node.id, "payload": payload})

# 4. Poll until DONE/FAILED
```

### Role-Based Timeouts

| Role | Timeout |
|---|---|
| `RAG` | 600 s |
| `SPECIALIST` | 600 s |
| `TOOLS` | 300 s |
| `SCHEMA` | 300 s |
| `PLANNER` | 300 s |
| `PRODUCTIVITY` | 300 s |
| `EMAIL` | 300 s |

---

## Worker Patterns

### A2A Bus Listener (Primary Path)

Workers call `self.bus.listen(AgentRole.<ROLE>.value)` in a `run_forever()` loop. On receiving a message containing `node_id`, they fetch the `Node` from `TreeStore` and call `_process_task(task)`.

```python
async def run_forever(self):
    while self._running:
        async for msg in self.bus.listen(AgentRole.RAG.value):
            node_id = msg.get("node_id")
            task = self.tree_store.get_node_by_id(node_id)
            await self._process_task(task)
```

### Thought Broadcasting

During the ReAct loop, each specialist publishes parsed thought text to the A2A Bus:

```python
await self.bus.publish(self.role.value, {
    "type": "thought",
    "content": clean_thought,
    "session_id": session_id
})
```

The coordinator subscribes to all roles at the start of each turn and forwards `thought` events to the WebSocket client via `status_callback`.

### Node Status Lifecycle

```
add_node_async() → PENDING
      ↓ (worker picks up)
update_node_status(PENDING, progress=...)   ← per-turn progress updates
      ↓
update_node_status(DONE, result={message: ...})   ← success
      OR
update_node_status(FAILED, result={error: ...})   ← failure
```

---

## Worker Startup

Specialist workers are started independently — either via Docker containers (see `docker-compose.yml`) or manually. The `scripts/` directory contains helper scripts for development. Each worker blocks on `asyncio.run(worker.run_forever())`.

> Last updated: arc_change branch — verified against source

