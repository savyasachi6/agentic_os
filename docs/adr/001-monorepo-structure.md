# ADR 001: Monorepo Structure with Subsystem Decoupling

## Status

Proposed

## Context

The Agent OS project has evolved from a single monolithic repository into a complex system with three core subsystems (`core`, `memory`, `skills`) and multiple specialized projects (DevOps, Robotics, etc.). We need a repository structure that allows for independent subsystem evolution while maintaining a coherent "Appliance" experience for the user.

## Decision

We will adopt a **Coordinated Monorepo** structure. The root directory acts as the "Appliance Console," while core subsystems are maintained as distinct directories that can also function as standalone Git repositories.

### Repository Hierarchy

- **Appliance Root**: Orchestrates the entire stack via `docker-compose.yml` and root-level documentation.
- **Subsystems (`agentos_*`)**: Each folder contains its own `pyproject.toml`, `README.md`, and logic. They communicate via well-defined APIs (FastAPI/REST/WebSocket).
- **Projects (`projects/*`)**: Specialized configurations and workspace-specific prompts/data that leverage the core subsystems.

## Alternatives Considered

### 1. Unified Monolith

- **Pros**: Simplest for single-developer workflows.
- **Cons**: Becomes brittle as dependencies for Robotics (ROS 2) and DevOps (Ansible/Docker) collide. Hard to deploy parts of the system independently.

### 2. Micro-repositories Only

- **Pros**: Maximum decoupling.
- **Cons**: Extremely high friction for users to set up the "Agent Appliance" (cloning 4+ repos, manual networking).

## Consequences

- **Pros**:
  - Subsystems can be worked on independently (e.g., a memory expert can focus on `agentos_memory`).
  - Clearer dependency graph.
  - Easier to test individual modules in isolation.
- **Cons**:
  - Requires disciplined cross-project import management (avoiding circular deps).
  - Documentation needs to be synced at both root and subsystem levels.
