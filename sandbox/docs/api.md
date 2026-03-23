# API Reference

## Modules

### `sandbox.manager`

Coordinates worker spawning and tracking.

- `SandboxManager()`: Instantiates the manager. Configured via `SandboxSettings` in environment.
- `manager.get_or_create(session_id: str) -> SandboxInfo`: Returns connection info, spinning up a worker if necessary.
- `manager.get_worker_url(session_id_or_sandbox_id: str) -> str`: Fetches only the base URL mapping.
- `manager.shutdown(sandbox_id: str)`: Sends SIGTERM to worker and unregisters it.
- `manager.shutdown_all()`: Destroys all currently tracked workers.

### `sandbox.worker`

The actual execution script. Invoked directly as a subprocess via `python -m sandbox.worker`.

- Exposes `GET /health` to confirm startup.
- Exposes `POST /tools/{tool_name}` accepting a `ToolRequest` JSON body.

### `sandbox.models`

State and wire protocol typing.

- `SandboxInfo`: Runtime tracking type (ports, pids, active status).
- `SandboxConfig`: Resource constraints (`max_memory_mb`, `timeout_seconds`).
- `ToolRequest`: Passed downwards `{"tool_name": "...", "args": {}}`.
- `ToolResponse`: Returned upwards `{"success": true, "result": {...}}`.
