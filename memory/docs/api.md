# API Reference — Agent Memory

## `agent_memory.db`

### `init_schema()`

Initializes the PostgreSQL database schema from `schema.sql`. Safe to call multiple times (uses `IF NOT EXISTS`).

### `get_db_connection()`

Context manager that yields a pooled database connection with `pgvector` pre-registered.

---

## `agent_memory.vector_store.VectorStore`

### `generate_embedding(text: str) -> List[float]`

Generates a 1024-dimensional embedding vector via the local Ollama instance.

### `upsert_skill(name, description, tags, path, eval_lift=0.0) -> int`

Inserts or updates a skill record. Returns the internal `skill_id`.

### `search_skills(query: str, limit: int = 8) -> List[Dict]`

Returns relevant skill chunks ranked by cosine similarity to the query.
Returns `{"skill_name", "content", "similarity_score", ...}`.

### `log_thought(session_id, role, content)`

Logs a thought, tool call, or message to the `thoughts` table with an automatic embedding for later recall.

---

## `agent_memory.tree_store.TreeStore`

### `create_chain(session_id, name) -> int`

Initializes a new execution chain (DAG) for a task.

### `add_command(lane_id, cmd_type, tool_name, args) -> str`

Appends a command to a specific lane for async execution.

### `get_next_pending(lane_id) -> Optional[Command]`

Retrieves the next priority command for a worker to execute.

---

## `agent_memory.models`

### `Node` (Pydantic Model)

Properties: `id`, `chain_id`, `node_type`, `content`, `status`, `metadata`.

### `Command` (Pydantic Model)

Properties: `id`, `lane_id`, `cmd_type`, `tool_name`, `args`, `status`, `result`, `error`.
