# Security & Sandboxing

## Authentication

The **Gateway** (`gateway/server.py`) is the single ingress point for all client connections. It enforces JWT-based authentication — requests without a valid token are rejected before reaching the `CoordinatorAgent`.

Internal agent-to-agent communication (via the **A2A Bus**) and database access do not carry per-request JWT tokens; they are process-local and operate within the same trust boundary.

## Tool Risk Tiers

Tool calls within the ReAct loop are classified by `RiskLevel` (`agent_core/agent_types.py`):

| Risk Level | Value | Execution Policy |
| :--- | :--- | :--- |
| `LOW` | `"low"` | Executed directly (in-process). |
| `NORMAL` | `"normal"` | Executed with basic subprocess isolation. |
| `HIGH` | `"high"` | Requires Sandbox execution + explicit user approval (Human-in-the-loop). |

## Fail-Fast Specialist Dispatch

The `BridgeAgent` performs a **heartbeat check** against Redis before dispatching any task to a specialist worker:

```python
is_alive = await self.bus.get_heartbeat(self.role.value)
if not is_alive:
    return {"error_type": "offline", "error": "Specialist agent is offline."}
```

This prevents the coordinator from hanging for the full role timeout (up to 600s) when a specialist container is down.

## Sandbox & Process Isolation

The `sandbox/` package provides an isolated execution environment for tool calls that interact with the local filesystem or shell. Key properties:

- **Process Isolation**: Tools run in separate subprocesses with restricted OS privileges.
- **Path Whitelisting**: The agent is restricted to designated project directories; access outside these paths is blocked.
- **Resource Limits**: CPU and memory limits can be configured per sandbox invocation.

## LLM Cloud Failover Circuit Breaker

The `LLMRouter` implements a **circuit breaker** for cloud backends:

- On HTTP 401 (Unauthorized) or 429 (Rate Limit), the router sets `_last_cloud_error_time`.
- For the subsequent **5 minutes**, all requests are automatically rerouted to the local Ollama fallback.
- This prevents cascading failures and unexpected costs from repeated cloud retry storms.

## Data Privacy

- **Local-First by Default**: All inference runs against a local Ollama/LlamaCPP instance unless `ROUTER_BACKEND=openai` is configured.
- **No Data Egress**: User queries and agent reasoning steps are stored only in the local PostgreSQL instance.
- **`pgvector` Embeddings**: All vectors are generated locally via the `Embedder` class; no external embedding API is called unless explicitly configured.

> Last updated: arc_change branch — verified against source

