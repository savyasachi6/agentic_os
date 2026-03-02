# ADR-007: Domain-Driven Module Isolation

## Status

Accepted

## Context

As we add more "Built-in Skills" like DevOps and Productivity, the risk of a "Big Ball of Mud" where every module depends on every other module increases.

## Decision

We organize business logic into **Domain Modules** within `agentos_core`.

1. **Strict Boundaries**: Each domain is a self-contained folder (`devops_auto`, `productivity`).
2. **Shared Foundation**: Domains can only depend on `agent_core` (the engine) and `agent_memory`/`agent_skills` (the infrastructure).
3. **No Cross-Domain Coupling**: `productivity` should never depend directly on `devops_auto`. If they need to interact, they must do so via the `Agent Core` loop or a shared event bus.

## Consequences

- **Positive**: High maintainability and testability of individual features.
- **Positive**: Easier to extract a domain into its own repository later if needed.
- **Negative**: May lead to some duplication of data models (e.g., "User" in both domains).
