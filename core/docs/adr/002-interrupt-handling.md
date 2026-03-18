# ADR-002: Interrupt Handling via Control Token

**Status:** Accepted  
**Date:** 2026-03-01

## Context

For a PersonaPlex-style agent, users need to interrupt mid-generation (e.g., via voice). The agent must stop, acknowledge, and incorporate the interrupt.

## Decision

Use a simple `interrupted` flag + `<INTERRUPT>` control token prepended to the user's interjection.

## Rationale

- **Simple**: No complex async cancellation. The ReAct loop checks the flag at each iteration boundary.
- **Deterministic**: The interrupt is queued as the next user message, maintaining correct message ordering.
- **Priority**: System prompt instructs the agent to treat the latest utterance as highest priority.

## Consequences

- Current Ollama calls are blocking; interrupts take effect after the current step completes.
- Streaming + async cancellation would be needed for true mid-token interruption.
