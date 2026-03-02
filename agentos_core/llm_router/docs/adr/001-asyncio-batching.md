# ADR 001: Asyncio Request Batching

## Status

Accepted

## Context

Agent OS needs to support dozens of concurrent agent sessions on a single machine. Direct calls to local inference APIs (like Ollama) from each agent result in serialized execution or GPU context switching overhead, significantly capping throughput. Consistent GPU saturation requires batching multiple requests into a single forward pass where possible.

## Decision

We implemented an **Asyncio-based Request Router** using the Singleton pattern.

1. **Async Queue**: Requests are enqueued as they arrive, allowing the agent reasoning loop to remain non-blocking.
2. **Batch Windows**: A short, configurable window (default 50ms) allows the router to "wait" for multiple requests before dispatching, without significantly impacting perceived latency.
3. **Future-based Resolution**: Each request is associated with an `asyncio.Future`, allowing the demuxer to return results to the specific caller immediately upon batch completion.

## Consequences

- **Fixed Latency Penalty**: Every request potentially waits up to 50ms (the batch window) even if the GPU is idle. This is a deliberate trade-off for higher peak throughput.
- **Centralized Failure**: If the Router loop crashes, all agents lose inference capabilities. This is mitigated by robust error handling and auto-restart logic.
- **Parameter Sensitivity**: Requests with different models or temperatures cannot be batched together in a single prompt-batch; the router groups them into separate backend calls.
