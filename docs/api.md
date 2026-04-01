# Global API & Orchestration Protocols

## Entry Points

### 1. WebSocket Interface — `gateway/server.py`

The primary real-time interaction layer.

- **Endpoint**: `ws://<host>:<port>/chat`
- **Protocol**: JSON Streaming
- **Message Types** (server → client):
  - `status`: Short status text (e.g., `"Classifying intent..."`, `"Polling specialist..."`)
  - `thought`: An internal reasoning step from a specialist's ReAct loop (streamed live).
  - `final_answer`: The complete final text response to the user.
  - `error`: Error payload if the coordinator or specialist fails.

### 2. REST Endpoints — `gateway/server.py`

> **Note**: The exact routes are defined in `gateway/server.py`. The endpoints below reflect the current implementation.

- **`POST /chat`**: Submit a synchronous task and receive a response (REST alternative to WebSocket).
- **`GET /v1/sessions/{id}/history`**: Retrieve the reasoning trace (chain + nodes) for a session.
- **`POST /v1/skills/index`**: Trigger re-indexing of the skills registry.

### 3. RL Router — `rl_router/server.py`

The standalone RL router runs as a separate service (port 8001 in Docker):

- **`POST /predict`**: Receive a query + context vector, return a bandit arm decision `{arm_index, depth, speculative}`.
- **`POST /reward`**: Submit a reward signal to update the bandit weights.

> **Current status**: These endpoints are not called by the main agent pipeline. The bandit is embedded in-process inside `CognitiveRetriever`.

---

## Orchestration Protocols

### ReAct (Reasoning and Acting)

All specialist workers use a strict ReAct format for every LLM turn:

```
Thought: <internal reasoning>
Action: <tool_name>(<arguments>)
```

The loop terminates when the agent calls:

```
Action: respond_direct(message="""<final answer>""")
```

#### Recovery Mechanisms
- **No-Action Nudge**: If no `Action:` line is parsed, a correction observation is injected.
- **Last-Turn Nudge**: On the second-to-last turn, the worker injects a forced `respond_direct` instruction.
- **Empty-Turn Skip**: An empty LLM response is skipped (not appended) to avoid context poisoning.

### A2A Bus Protocol (Redis)

The coordinator and specialist workers communicate via Redis pub/sub channels keyed by `AgentRole` value:

```
Coordinator  →  bus.send("rag", {node_id, payload})   # Dispatch
Specialist   →  bus.publish("rag", {type:"thought", content, session_id})  # Stream thoughts
Coordinator  ←  bus.subscribe("rag", handler)         # Receive thoughts
```

Heartbeats are published by workers to a separate Redis key and checked by `BridgeAgent` before each dispatch.

### Batch Inference (LLM Router Protocol)

The `LLMRouter` implements a collect-and-dispatch protocol:

1. **Submit**: Agents call `LLMClient.generate_async()` → `LLMRouter.submit()`, which enqueues an `LLMRequest`.
2. **Batch**: The background `_batch_loop()` groups pending requests by `(model, max_tokens, temperature, stop_sequences)`.
3. **Dispatch**: Grouped requests are sent as a single batch to the active backend.
4. **Demux**: Individual results are matched back to their originating agent `asyncio.Future` by `request_id`.

### TreeStore Node Lifecycle

Every task dispatched through `BridgeAgent` is persisted as a database `Node`:

```
PENDING → (worker picks up) → RUNNING → DONE
                                       ↘ FAILED
```

The coordinator polls node status every 0.5s until terminal status or role-based timeout.

> Last updated: arc_change branch — verified against source

