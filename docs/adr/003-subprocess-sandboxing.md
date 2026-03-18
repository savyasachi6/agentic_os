# ADR 003: Subprocess Sandboxing for Tool Execution

## Context

Executing arbitrary shell commands, Python scripts, or file I/O operations directly within the main `core` process is a significant security and stability risk. A single crashed tool or a malicious command could compromise the entire reasoning engine.

## Decision

We chose to implement **Subprocess Sandboxing** using a dedicated `SandboxManager`.

- **Isolation**: Every tool invocation that interacts with the host OS (Shell/File) is executed in a separate, short-lived subprocess or a managed worker process.
- **Worker Pattern**: High-risk sessions are mapped to isolated FastAPI "Worker" processes that expose restricted REST endpoints for tool calling.
- **Restriction**: Workers are started with limited filesystem access and non-privileged roles.

## Rationale

- **Security**: Prevents "breaking out" of the agent's reasoning loop. If a tool call is malicious or destructive, the damage is capped at the worker/subprocess level.
- **Stability**: Resource leaks (memory, fd) or hang-ups in a tool do not affect the `core` process. The manager can simply kill and restart a misbehaving worker.
- **Observability**: Every tool call to a worker is an HTTP request, providing a clear audit log of all system interactions.

## Consequences

- **Overhead**: Spawning and managing subprocesses/workers incurs a performance penalty compared to direct function calls.
- **Complexity**: Reasoning about IPC (Inter-Process Communication) and state synchronization between the Core and the Workers is more complex.
