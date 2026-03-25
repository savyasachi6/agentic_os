# ADR-005: Batching at LLM Router

## Status

Accepted

## Context

When multiple agents or async processes (like voice turns and tool loops) are active, they all compete for GPU/LLM resources. Naive sequential execution leads to high latency for the last requester.

## Decision

We implement a centralized `LLMRouter` that sits between all agents and the LLM backend.

- All LLM requests must be submitted to the router.
- The router groups compatible requests (same model, similar token limits) into micro-batches.
- The router handles the wait time (50ms) to maximize batch density.
- The router demultiplexes the response chunks back to the original callers.

## Consequences

- **Positive**: Significantly higher throughput; reduced per-request wait time under load.
- **Positive**: Decouples the agent logic from the specific batching capabilities of the backend (Ollama vs vLLM).
- **Negative**: Adds a small constant overhead (batch interval) to single-request latency.
- **Negative**: Increases complexity in the agent core/client relationship.
