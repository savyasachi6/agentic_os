# Agent Roles and Workers

This document maps the logical agents in Agentic OS to their `AgentRole`, A2A topics, and worker implementations.

## Agent Mapping

| Agent Role | Specialist File | Entry Point / Class | Description |
| :--- | :--- | :--- | :--- |
| `rag` | `agents/rag_agent.py` | `ResearchAgentWorker` | Research, fact-checking, and long-term memory retrieval. |
| `tools` | `agents/code_agent.py` | `CodeAgentWorker` | General code execution and systems tasks. |
| `schema` | `agents/capability_agent.py` | `CapabilityAgentWorker` | Fast-path capability queries and skill discovery. |
| `email` | `agents/email_agent.py` | `EmailAgent` | Email management and notifications. |
| `productivity` | `agents/productivity.py` | `ProductivityAgent` | Calendar, tasks, and notes management. |
| `specialist` | `agents/executor.py` | `ExecutorAgentWorker` | Generic specialized task execution. |
| `planner` | `agents/planner.py` | `PlannerAgentWorker` | High-level strategy and breakdown of complex tasks. |

## Routing & Dispatch

### Logical Intent Routing
- **`memory` intent**: Currently routes directly to the `rag` worker via the `BridgeAgent` to leverage the `CognitiveRetriever`.
- **`code_gen` intent**: Routes to the `tools` worker with a code-specific retrieval policy.

### BridgeAgent & Heartbeats
The `BridgeAgent` in `coordinator.py` acts as a dispatcher to background workers. Before dispatching a task to the `A2ABus`, it performs a **heartbeat check**:

```python
if self.bus:
    is_alive = await self.bus.get_heartbeat(self.role.value)
    if not is_alive:
        return {"error_type": "offline", "error": "Specialist agent is offline."}
```

This ensuring "fail-fast" behavior if a required specialist worker is not running.

## Worker Patterns

Most specialist workers are started by `scripts/worker_manager.py`. It uses the `AgentWorker` class as a poller wrapper around agent implementations, checking the `TreeStore` for `PENDING` nodes while simultaneously listening for "Fast-Path" notifications on the **A2A Bus** (Redis).

> Last updated: arc_change branch
