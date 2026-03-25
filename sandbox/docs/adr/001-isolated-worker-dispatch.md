# ADR 001: Subprocess Worker Dispatch

## Status

Accepted

## Context

When an LLM agent executes a tool (for example: running bash, executing a python snippet, or parsing a massive file), it poses three risks to the host reasoning engine:

1. **Blocking**: The tool call could hang infinitely.
2. **Memory Exhaustion**: The tool might load a massive file and trigger OOM.
3. **Crashing**: The tool could encounter a segfault, tearing down the ReAct loop process.

## Decision

Instead of executing python functions directly in the ReAct event loop thread, we isolate execution by mapping `session_id` directly to parallel Python background process workers (`sandbox.worker`), which communicate via a standardized HTTP JSON envelope (`ToolRequest` / `ToolResponse`).

1. **Why HTTP?**: HTTP is simpler than setting up highly-coupled Python `multiprocessing.Queue` or pipes. It allows the `LaneRunner` to interact with workers network-transparently.
2. **Why Subprocesses?**: Compared to Docker containers, standard python subprocesses spin up extremely fast (sub 500ms). Perfect for localized ReAct execution without extensive VM overhead natively on Windows and Mac.

## Consequences

- Requires continuous management of dangling or frozen Python processes via `SandboxManager`.
- Currently runs code under the same OS privileges as the parent app. In future iterations, we may migrate to Docker containers or `.NET` restricted contexts for full OS-level isolation while preserving the identical HTTP tool request interface.
