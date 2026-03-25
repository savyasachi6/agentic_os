# Component: Lane Queue

## Responsibility

The `lane_queue` provides a durable, asynchronous task execution layer for the `core`. It ensures that complex, multi-step operations can be tracked, retried, and executed without blocking the main reasoning loop.

## Key Submodules

### [Store](file:///c:/Users/savya/projects/agentic_os/core/lane_queue/store.py)

The persistence layer. It manages the lifecycle of `Lanes` and `Commands` in the SQL database, providing transactional integrity for task state transitions (Pending → Running → Done/Failed).

### [Runner](file:///c:/Users/savya/projects/agentic_os/core/lane_queue/runner.py)

The execution engine. It polls the store for pending commands and dispatches them to the appropriate resolver (e.g., the Sandbox tool client or an internal function).

### [Models](file:///c:/Users/savya/projects/agentic_os/core/lane_queue/models.py)

Defines the core data structures:

- **Lane**: A sequential or parallel container for commands, scoped to a session and risk level.
- **Command**: An atomic unit of work (LLM call, Tool call, or Human review).

## Integration

The `LocalAgent` uses the `LaneQueue` for all non-trivial tool executions. When the agent decides to use a tool, it enqueues a `Command` into the current session's `Lane`.
