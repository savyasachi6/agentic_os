# Architecture Overview

`sandbox` architecture separates the lifecycle management (the Manager) from the actual execution engine (the Worker).

## Data Flow

```mermaid
graph TD
    Client[Lane Runner / Agent Loop] -->|get_or_create(session)| Manager[SandboxManager]
    Manager -->|Spawns Subprocess| Worker1[Worker Process :9100]
    Manager -->|Spawns Subprocess| Worker2[Worker Process :9101]
    
    Client -->|HTTP POST /tools/name| Worker1
    Worker1 -->|Execute| OS[Local OS / Storage]
    Worker1 -->|HTTP 200 Tool Response| Client
```

## Subsystem Details

1. **The Manager (`manager.py`)**: Runs in the parent process. Maintains a `dict` mapping session IDs to `SandboxInfo`. It handles launching new workers (`subprocess.Popen`), checking HTTP health, and shutting them down gracefully or via `SIGKILL`.
2. **The Worker (`worker.py`)**: A standalone `fastapi` script. It initializes the `agent_core.tools` registry and exposes an endpoint `/tools/{tool_name}`. It enforces maximum memory boundaries.
3. **The Models (`models.py`)**: Pydantic types bridging state tracking and JSON wire definitions (`ToolRequest`, `ToolResponse`, `SandboxInfo`).
