# ADR-003: Centralized LLM Router for Multi-Agent Inference

## Status

Accepted

## Context

In a multi-agent or multi-session environment, individual agents frequently request small inference tasks (Reasoning, Summarization, Embedding). If each agent session calls the local LLM (Ollama) directly:

1. **GPU Underutilization**: Multiple small requests arrive sequentially, missing the opportunity for batching.
2. **Request Contention**: Requests may block each other at the Ollama API level, leading to high tail latency.
3. **Priority Inversion**: A background summarization task might block a high-priority user thought step.

## Decision

Implement a **Centralized LLM Router** (`llm_router/`) as a process-level singleton.

- **Batching**: The router waits for a short interval (e.g., 50ms) to collect incoming requests and merges them as parallel prompts where the provider (vLLM/LPX) supports it.
- **Priority Queue**: Implements high/medium/low priority lanes. `Thought` steps are high priority; `Summarization` is low.
- **Model Multiplexing**: If multiple local models are running (e.g., Llama 3 and Qwen), the router directs traffic based on the "fast" vs "reasoning" classification.

## Consequences

- **Pros**: Significantly higher throughput; more predictable latency; better GPU saturation.
- **Cons**: Adds 50ms of overhead (the batching window) to every request; increased complexity in the `LLMClient`.
- **Mitigation**: The batching window is configurable via `ROUTER_BATCH_INTERVAL_MS`. For single-user dev modes, it can be set to 0.

## Implementation Details

The `LLMClient` no longer calls `ollama.chat` directly. It calls `router.submit()`, which returns a Future (or awaits an Event).
