# LLM Router — Internal Component

## Responsibility

The **LLM Router** (implemented in `llm_router/router.py`) is responsible for mediating all requests between the agent reasoning loop and the local LLM backend (Ollama, vLLM). It optimizes throughput via micro-batching.

## Key Features

- **Micro-Batching**: Groups concurrent requests into small batches (default: 8) to reduce GPU context switching.
- **Backend Abstraction**: Provides a unified interface for multiple local inference providers.
- **Queueing**: Prevents overloading the LLM process by managing a finite request buffer.
- **Latency Balancing**: Configurable wait intervals (e.g., 50ms) to maximize batch density without sacrificing interactivity.

## Boundary & Dependencies

### Inbound

- **Agent OS Core**: Submits prompts for completion via the ReAct reasoning loop.

### Outbound

- **Local LLM Backend**: Executes the batched inference.
- **Prometheus/Metrics** (Future): Reports on batch efficiency and latency.

## Extensions

- **New Backends**: Can be extended by adding new subclasses in `llm_router/backend.py`.
- **Dynamic Batching**: Future support for adaptive wait times based on system load.

## Important Invariants

- **Request Context**: Every request must maintain its original user/session ID through the batch cycle.
- **Thread Safety**: The router singleton must handle concurrent requests from multiple agent threads.

## Related Documentation

- [Global Architecture](../../docs/architecture.md)
- [Component: Reasoning Engine](reasoning_engine.md)
