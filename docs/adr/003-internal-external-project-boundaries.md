# ADR 003: Internal/External Project Boundaries

## Status

Proposed

## Context

As the Agentic OS ecosystem grows, the distinction between "Service" (independent repository/process) and "Module" (internal component of a service) was becoming blurred. For example, `DevOps Automation` and `Personal Productivity` were sometimes discussed as standalone agents, yet they share the same ReAct loop and infrastructure as the Core.

## Decision

We will enforce a strict hierarchy of projects:

1. **Global Services (Repos)**: `Agent OS Core`, `Agent Memory`, and `Agent Skills` are the primary services. They are decoupled by process and network boundaries.
2. **Internal Projects (Modules)**: Features like `DevOps`, `Productivity`, and `Voice` are internal modules *within* `Agent OS Core`. They share the memory space and reasoning loop of the Core to minimize latency and orchestration overhead.
3. **External Solutions (Projects)**: The `projects/` directory in the root repository contains specialized configurations or "solution templates" that use the Global Services.

## Alternatives Considered

- **Microservices for everything**: Decoupling DevOps into its own service would allow independent scaling but would double the complexity of the "System of Systems" communication protocol for no immediate gain in throughput.

## Consequences

- **Positive**: Clearer documentation paths for developers. Easier testing of the Core as a single reasoning unit.
- **Negative**: Internal modules are tightly coupled to the Core's `AgentState` and `ReActLoop` implementation.
