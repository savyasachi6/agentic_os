# Agent Roles and Workers

This document maps the logical agents in Agentic OS to their `AgentRole`, A2A topics, and worker implementations.

## Agent Mapping

| Agent Name | AgentRole | A2A Topic (if used) | Worker Module | Entry Point / Class | Startup Method |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Research** | `AgentRole.RAG` | `research` | `agents/rag_agent.py` | `ResearchAgentWorker` | `worker_manager.py` (via `AgentWorker`) |
| **Code** | `AgentRole.TOOLS` | `code` | `agents/code_agent.py` | `CodeAgentWorker` | `worker_manager.py` (via `AgentWorker`) |
| **Capability** | `AgentRole.SCHEMA` | `capability` | `agents/capability_agent.py` | `CapabilityAgentWorker` | `worker_manager.py` (via `AgentWorker`) |
| **Executor** | `AgentRole.SPECIALIST` | `specialist` | `agents/executor.py` | `ExecutorAgentWorker` | `worker_manager.py` (via `AgentWorker`) |
| **Planner** | `AgentRole.PLANNER` | `planner` | `agents/planner.py` | `PlannerAgentWorker` | **MISSING** |
| **Productivity** | `AgentRole.PRODUCTIVITY` | `productivity` | `agents/productivity.py` | `ProductivityAgent` | `worker_manager.py` (via `AgentWorker`) |
| **Email** | `AgentRole.EMAIL` | `email` | `agents/email_agent.py` | `EmailAgent` | `worker_manager.py` (via `AgentWorker`) |
| **Memory** | `AgentRole.RAG` | `research` | `agents/rag_agent.py` | `ResearchAgentWorker` | Shared with Research |
| **RAG** | `AgentRole.RAG` | `research` | `agents/rag_agent.py` | `ResearchAgentWorker` | `worker_manager.py` (via `AgentWorker`) |

## Startup Governance

### Worker Manager

Most specialist workers are started by `scripts/worker_manager.py`. It uses the `AgentWorker` class (from `agents/worker.py`) as a poller wrapper around the agent implementations.

### Polling vs. Listening
- **Polling (`AgentWorker`)**: Periodically checks the `TreeStore` (DB) for `PENDING` nodes of a specific role.

- **Listening (`A2ABus`)**: Many agents (`ResearchAgentWorker`, `ExecutorAgentWorker`, `CapabilityAgentWorker`) have a `run_forever` method that listens to an A2A bus (Redis). However, `worker_manager.py` currently favors the polling wrapper for most roles.

## Missing Workers
- **Planner Agent**: `PlannerAgentWorker` in `agents/planner.py` is not currently instantiated or started by `worker_manager.py`.
