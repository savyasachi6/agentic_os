# Reasoning Engine — Internal Component

## Responsibility

The **Reasoning Engine** (implemented in `agent_core/loop.py`) is the heart of the Agent OS. It orchestrates the ReAct loop, managing the transition between Thought, Action, and Observation.

## Key Features

- **Asynchronous ReAct**: Non-blocking step execution allowing for user interrupts.
- **Context Management**: Aggregates system prompts, session history, and RAG context from `AgentOS Skills`.
- **Interrupt Handling**: Inspects for `<INTERRUPT>` tokens between thought cycles to incorporate real-time user feedback.
- **Instruction Mapping**: Translates raw LLM text into enqueued actions or final responses.

## Boundary & Dependencies

### Inbound

- **Server/CLI**: Submits user messages and starts the loop.
- **WebSockets**: Streams partial thoughts to the frontend.

### Outbound

- **LLM Router**: Proxies all inference requests.
- **Lane Queue**: Enqueues tool calls for execution.
- **Skills Retriever**: Fetches contextual data for RAG.

## Extension Points

1. **Custom Scaffolding**: New `SKILL.md` files can define specialized reasoning structures that the engine automatically follows via the system prompt.
2. **Parser Hooks**: The engine can be extended with new regex patterns for specialized output formats.

## Important Invariants

- **Session Isolation**: Every loop iteration MUST be associated with a `session_id`.
- **Iteration Cap**: Loops are hard-capped (default: 10) to prevent infinite reasoning cycles.
