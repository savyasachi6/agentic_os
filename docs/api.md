# Global API & Orchestration Protocols

## Entry Points

### 1. WebSocket Interface (`/chat`)

The primary real-time interaction layer for agents.

- **Endpoint**: `ws://<host>:<port>/chat`
- **Protocol**: JSON Streaming
- **Message Types**:
  - `user_message`: Submit text/intent.
  - `agent_thought`: Internal reasoning step (Thought/Action).
  - `tool_result`: Observation from a tool call.
  - `final_answer`: Final text response to user.

### 2. REST API

- **`POST /v1/agent/task`**: Submit a long-running background task to the `lane_queue`.
- **`GET /v1/sessions/{id}/history`**: Retrieve the full reasoning trace for a session.
- **`POST /v1/skills/index`**: Trigger a re-indexing of the `skills/` directory.

## Orchestration Protocols

### ReAct (Reasoning and Acting)

Agent OS components communicate via a standardized ReAct protocol:

1. **Thought**: The Core describes its plan.
2. **Action**: The Core requests a tool execution targeting a `sandbox`.
3. **Observation**: The `sandbox` returns the result to the Core.
4. **Repeat**: The loop continues until a `Final Answer` is reached.

### Batch Inference (Router Protocol)

The `LLM Router` implement an internal "collect-and-dispatch" protocol:

- **Submit**: Agents submit `LLMRequest` (messages, params) to the router's async queue.
- **Batch**: The router groups pending requests by model and hyperparameters every 50ms.
- **Mux/Demux**: The router dispatches a single batch request to the backend and maps individual results back to the originating agent's `Future`.

### Secure Tool Execution

Tools are invoked via a signed HTTP POST:

- **Target**: `http://sandbox:<port>/tools/{tool_name}`
- **Payload**: JSON arguments.
- **Response**: Standardized `ToolResponse` (stdout, stderr, exit_code, result).
