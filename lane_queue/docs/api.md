# API Reference

## Modules

### `lane_queue.store`

Manages the CRUD operations against PostgreSQL.

- `CommandStore.create_lane(session_id: str, name: str) -> Lane`: Creates a new execution queue.
- `CommandStore.enqueue(lane_id: str, cmd_type: CommandType, payload: dict) -> Command`: Safely inserts a command at the tail of the lane.
- `CommandStore.claim_next(lane_id: str) -> Command | None`: Claims the next pending command via row-level locking.
- `CommandStore.complete(command_id: str, result: dict)`: Marks command `DONE` and attaches JSON result.

### `lane_queue.runner`

A daemon thread polling for tasks.

- `LaneRunner(lane_id, store, llm, sandbox_resolver)`: Initializes a runner context.
- `LaneRunner.start()`: Runs the loop in a background thread.
- `LaneRunner.run_once() -> Command | None`: Executes exactly one command synchronously (useful for tests/step-through).

### `lane_queue.models`

Types.

- `Command`: Pydantic object representing an execution row.
- `CommandType`: Enum (`LLM_CALL`, `TOOL_CALL`, `HUMAN_REVIEW`).
- `CommandStatus`: Enum (`PENDING`, `RUNNING`, `DONE`, `FAILED`, `CANCELLED`).
