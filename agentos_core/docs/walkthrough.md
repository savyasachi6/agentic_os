# Agent OS Core — System Walkthrough

Welcome to the internal structure of the **Agent OS Core**. This document provides a developer-friendly tour of how a user request translates into reasoning and secure action across our modular architecture.

## 1. The Entry Point

A user request arrives via `main.py` or `server.py`. It initializes a `LocalAgent` (from `agent_core/loop.py`) which holds the `AgentState` for the current `session_id`.

## 2. Context Building (The Librarian Step)

Before thinking, the agent calls:

- **Skills**: `agent_skills.retriever` (RAG hits for specific prompt recipes).
- **Memory**: `agent_memory.vector_store` (Pulls prior reasoning steps from "long-term memory").

## 3. High-Concurrency Reasoning (The Thinker)

The `LocalAgent` enters its ReAct loop. All inference asks are sent to the `LLMRouter` (`llm_router/`).

- **Batching**: The router might wait 50ms to merge this "Thought" step with a "Summarization" step from another session.
- **Streaming**: Tokens stream back to the UI/Voice pipeline immediately via async generators in `LLMClient`.

## 4. Secure Action Execution (The Doer)

When the LLM decides on an `Action`, the agent core dispatches it:

- **Infrastructure Tasks**: Handled by the `lane_queue/`. A background `runner.py` claims the command.
- **Domain Tasks**:
  - `devops_auto/`: For git, build, or deploy operations.
  - `productivity/`: For notes, todos, or briefing synthesis.
- **Isolation**: Every tool runs inside the `sandbox/` layer, using fresh worker processes to prevent host leakage.

## 5. Security Checkpoint

Before any high-risk tool is executed (e.g., `run_shell`), the `ToolClient` requests a scoped JWT from `security/jwt_auth.py`. The sandbox environment validates this token before allowing the operation.

## 6. Feedback & Loop

The "Observation" from the tool (e.g., "Build succeeded") is logged back to `AgentState` and `agent_memory`. The agent uses this new information to decide on the next step or provide the `Final Answer`.

---

## Technical Shortcuts

- **Wanna see the code hierarchy?** Check the root [README](../README.md).
- **Wanna see the design principles?** Read [architecture.md](./architecture.md).
- **Wanna see the Why?** Check [docs/adr/](./adr/).
