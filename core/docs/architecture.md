# Agent OS Core: Architecture

## Overview

**Agent OS Core** is the primary orchestration and execution engine of the Agentic OS ecosystem. It manages the agent's reasoning loop, schedules tasks via persistent queues, and executes system interactions through isolated tool nodes.

## Main Components

### 1. [ReAct Reasoning Loop](file:///c:/Users/savya/projects/agentic_os/core/agent_core/loop.py)

The central control loop. It follows the "Reason + Act" pattern, interpreting user intent, retrieving skills, and decomposing complex goals into atomic tool calls.

### 2. [Lane Queue Engine](file:///c:/Users/savya/projects/agentic_os/core/lane_queue)

A durable task orchestration layer. It allows the agent to enqueue multiple concurrent execution "lanes," supporting background processing and complex multi-step workflows.

### 3. [Sandbox Tool Manager](file:///c:/Users/savya/projects/agentic_os/core/sandbox)

Manages the lifecycle of isolated tool execution nodes. It spawns sandboxed subprocesses (or containers) for potentially high-risk actions, ensuring system integrity.

### 4. [Security & Auth](file:///c:/Users/savya/projects/agentic_os/core/security)

Enforces the appliance's security policy through JWT issuance, RBAC scope checks, and internal mTLS.

## High-Level Domain Modules

The Core includes specialized modules that extend the agent's capabilities into specific functional domains:

- **[DevOps Auto](file:///c:/Users/savya/projects/agentic_os/core/devops_auto)**: Automated CI/CD, PR management, and deployment orchestration.
- **[Productivity](file:///c:/Users/savya/projects/agentic_os/core/productivity)**: Personal task management, daily briefings, and workspace knowledge integration.

## Data Flow (Internal)

1. **Request**: Received via WebSocket or HTTP gatekeeper.
2. **Plan**: ReAct loop determines the next action.
3. **Queue**: Action is converted into a `Command` and pushed to a specific `Lane`.
4. **Execute**: `LaneRunner` dispatches the command to the `Sandbox` with a signed JWT.
5. **Observe**: Result is returned to the loop for the next reasoning step.

## 🔄 Execution Flow (`main.py` -> `server.py`)

When launching the Agent OS with `python main.py serve`, the system follows this boot sequence to orchestrate reasoning, routing, and tool execution:

### 1. The CLI Entry Point (`main.py`)

1. **Environment Initialization:** Loads `.env` using `dotenv` to ingest global settings like DB credentials and backend configuration early.
2. **Command Parsing:** Interprets the user's subcommand (e.g., `serve`, `cli`, `index`) using `argparse`.
3. **Backend Override:** Dynamically overrides `llm_router_settings.backend` to ensure `serve` utilizes `ollama` and `cli` utilizes `llama-cpp`.
4. **Uvicorn Start:** Handoffs execution to `uvicorn`, instructing it to serve the FastAPI `app` defined in `server.py`.

### 2. The FastAPI Server (`server.py`)

1. **App Lifecycle Hook (`startup` event):** Before accepting web traffic, FastAPI initializes the core infrastructure:
    - Calls `init_schema()` to guarantee the PostgreSQL DB and `pgvector` tables exist.
    - Evokes `LLMRouter.get_instance().start()` to boot the background batched generation loop.
    - Spawns background specialist agents (`SQLAgentWorker`, `CodeAgentWorker`, `ResearcherAgentWorker`) that continuously poll the durable Tree Store for work.
2. **Chat Connection (`/chat` WebSocket):**
    - When the Streamlit UI connects, it generates a stateful `CoordinatorAgent` session.
    - User messages trigger `agent.run_turn_async()`, kicking off the ReAct reasoning loop.
    - A `ws_callback` streams the Coordinator's internal thoughts and delegated task observations explicitly back to the UI in real-time.
3. **Graceful Shutdown:** On interrupt (`CTRL+C`), the server drains and cancels the background worker agents and stops the LLM Router cleanly.

---

## Further Reading

- [Global System Architecture](../../docs/architecture.md)
- [Project Boundaries (ADR-003)](../../docs/adr/003-internal-external-project-boundaries.md)
- [DevOps Documentation](../devops_auto/README.md)
- [Productivity Documentation](../productivity/README.md)
