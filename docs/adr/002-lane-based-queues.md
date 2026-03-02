# ADR 002: Durable Lane-Based Command Queuing

## Context

In a distributed agentic system, the reasoning loop (thinking) and side-effect execution (acting) must be decoupled for reliability. Commands (e.g., shell, file-write, API-calls) can take varying amounts of time and may fail due to transient environmental issues.

## Decision

We chose to implement a **Durable Lane-Based Command Queue** inside `agentos_core`.

- **Durable**: Every command is persisted to the `agentos_memory` SQL store before execution.
- **Lane-Based**: Commands are grouped into "lanes" (e.g., `bash`, `python`, `devops`). A single lane provides sequential execution within that context, while multiple lanes can run in parallel without race conditions.

## Rationale

- **Reliability**: If the main agent process crashes, pending commands are not lost; they remain "unclaimed" in the database.
- **Concurrency Control**: Different "lanes" allow us to isolate high-throughput background tasks (e.g., indexing) from immediate interactive tasks (e.g., user-requested bash commands).
- **Auditability**: Having a durable log of every command, its status (pending, claimed, finished), and its result provides a perfect audit trail for debugging and security profiling.

## Consequences

- **Complexity**: This adds a dependency on a persistent storage layer (PostgreSQL) for command management.
- **Latency**: There is a minor overhead in the command-loop for database I/O compared to an in-memory queue.
