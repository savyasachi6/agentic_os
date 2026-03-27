# Lane Queue

Database-backed, multi-lane command queue engine for the Agent OS.

## Purpose

`lane_queue` handles reliable execution of LLM and Tool tasks across multiple concurrent sessions (lanes). By decoupling command intent from command execution, the Agent OS can scale horizontally, support long-running tool calls without blocking the main event loops, and cleanly manage batch LLM execution requests.

## Key Features

- **Multi-Lane Segregation**: Commands are separated into session-specific lanes, executed in exact sequence order.
- **Robust State Machine**: Tracks commands across `pending`, `running`, `done`, `failed`, or `cancelled` states.
- **Transactional Consistency**: Uses PostgreSQL `FOR UPDATE SKIP LOCKED` for rock-solid concurrency management.
- **Decoupled Handlers**: Dispatches tool commands to isolated `sandbox` workers and reasoning commands to `agent_core.llm`.

## Target Users

Backend developers, ML platform engineers constructing queue-based orchestrators, and AI researchers building batch-execution agentic pipelines requiring guaranteed execution ordering and restartable tasks.

## Setup and Installation

### Prerequisites

- Python 3.11+
- A running PostgreSQL database with the Agent OS schema (from `agent_memory`)
- `agent_core` and `sandbox` packages in your Python path

### Installation

No specific PyPI package yet. Import as a local module:

```bash
# Ensure agentic_os is in your PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/agentic_os"
```

### Basic Usage Example

```python
from core.lane_queue.store import CommandStore
from core.lane_queue.models import CommandType
from core.lane_queue.runner import LaneRunner
from core.agent_core.llm import LLMClient

# 1. Initialize store (requires DB pool initialized)
store = CommandStore()

# 2. Create a session lane
lane = store.create_lane(session_id="user_session_abc", name="RAG_Agent_Lane")

# 3. Enqueue a task
cmd = store.enqueue(
    lane_id=lane.id,
    cmd_type=CommandType.LLM_CALL,
    payload={"messages": [{"role": "user", "content": "Hello!"}]}
)
print(f"Enqueued command: {cmd.id} at sequence {cmd.seq}")

# 4. Start the queue runner daemon for this lane
llm = LLMClient()
runner = LaneRunner(lane_id=lane.id, store=store, llm=llm)
runner.start()

# ... queue runner consumes the task asynchronously ...
# (Shut down when done)
runner.stop()
```
