# agent_core — API Reference

## Primary Classes

### `agent_core.loop.LocalAgent`

The main reasoning orchestrator.

- `run_turn_async(user_input: str) -> str`: Orchestrates a single turn (Thinking + Actions).
- `enqueue_tool_call(tool_name: str, args: Dict)`: Submits an action to the `lane_queue`.

### `agent_core.llm.LLMClient`

Wrapper for local model interaction via the `LLMRouter`.

- `generate_async(messages)`: Non-blocking generation.
- `generate_streaming(messages)`: Async iterator for tokens.

### `agent_core.state.AgentState`

Session and history manager.

- `add_message(role, content)`: Updates history and persists to memory.
- `compact_history(llm)`: Auto-summarization of long histories.

## Infrastructure Layers

### `llm_router.router.LLMRouter`

- `submit(messages, priority)`: Enqueues a task for the batcher.
- `get_instance()`: Singleton access point.

### `lane_queue.store.CommandStore`

- `enqueue(lane_id, type, payload)`: Adds a command to the queue.
- `claim_next(lane_id)`: Reserves a command for execution.

### `sandbox.manager.SandboxManager`

- `get_or_create(session_id)`: Resolve a session to an active worker.

### `security.jwt_auth`

- `create_tool_token(scope)`: Generates a scoped JWT for tool node access.

## Domain Projects

### `devops_auto`

- See [devops_auto/docs/api.md](../devops_auto/docs/api.md) for full reference.

### `productivity`

- See [productivity/docs/api.md](../productivity/docs/api.md) for full reference.

### `voice`

- See [voice/docs/api.md](../voice/docs/api.md) for full reference.
