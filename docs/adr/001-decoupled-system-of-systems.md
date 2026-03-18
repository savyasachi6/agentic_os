# ADR-001: Decoupled System-of-Systems Repository Structure

## Status

Accepted

## Context

The Agentic OS is growing in complexity, with distinct concerns for reasoning, persistence, and capability management. A monolithic repository:

1. Creates tight coupling between unrelated components (e.g., audio drivers vs. SQL schemas).
2. Makes it difficult to reuse the "Memory" or "Skills" layers in other projects.
3. Increases build and test times as the codebase grows.

## Decision

We adopt a **System-of-Systems** approach using a collection of decoupled repositories:

1. **`core`**: The orchestrator.
2. **`memory`**: The data layer.
3. **`skills`**: The capability layer.

Each repository is an independent Git project with its own lifecycle, versioning, and documentation. They are coordinated via a central "root" workspace (this directory) and orchestrated using Docker Compose.

## Consequences

- **Positive**: High cohesion and low coupling.
- **Positive**: Components can be developed and tested in isolation.
- **Positive**: "Memory" and "Skills" can be published as standalone libraries/services.
- **Negative**: Increased complexity in cross-repo dependency management (requires consistent env vars and networking).
- **Negative**: Requires careful documentation to maintain a "unified" developer experience.
