# ADR-003: Long-Lived Agent Event Loop

**Status:** Accepted  
**Date:** 2026-03-01

## Context

We needed to decide on the agent execution model. Options:

1. **One-shot execution**: Stateless per-task generation.
2. **Long-lived event loop**: Persistent session, multi-turn support.
3. **Stateless HTTP API**: Request/Response based.

## Decision

We chose the **long-lived event loop** (OpenClaw-style).

## Rationale

- **Multi-turn reasoning**: Complex tasks (RL, debugging) require recursive refinement.
- **State persistence**: `AgentState` maintains context and logs thoughts to long-term memory.
- **Interruption support**: Direct mapping to voice assistant interaction models.

## Consequences

- The agent process must manage its own lifecycle (daemon/service).
- Memory management requires explicit history compaction.
