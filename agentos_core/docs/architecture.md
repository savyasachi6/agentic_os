# Agent OS Core: Architecture

## Overview

**Agent OS Core** is the primary orchestration and execution engine of the Agentic OS ecosystem. It manages the agent's reasoning loop, schedules tasks via persistent queues, and executes system interactions through isolated tool nodes.

## Main Components

### 1. [ReAct Reasoning Loop](file:///c:/Users/savya/projects/agentic_os/agentos_core/agent_core/loop.py)

The central control loop. It follows the "Reason + Act" pattern, interpreting user intent, retrieving skills, and decomposing complex goals into atomic tool calls.

### 2. [Lane Queue Engine](file:///c:/Users/savya/projects/agentic_os/agentos_core/lane_queue)

A durable task orchestration layer. It allows the agent to enqueue multiple concurrent execution "lanes," supporting background processing and complex multi-step workflows.

### 3. [Sandbox Tool Manager](file:///c:/Users/savya/projects/agentic_os/agentos_core/sandbox)

Manages the lifecycle of isolated tool execution nodes. It spawns sandboxed subprocesses (or containers) for potentially high-risk actions, ensuring system integrity.

### 4. [Security & Auth](file:///c:/Users/savya/projects/agentic_os/agentos_core/security)

Enforces the appliance's security policy through JWT issuance, RBAC scope checks, and internal mTLS.

## High-Level Domain Modules

The Core includes specialized modules that extend the agent's capabilities into specific functional domains:

- **[DevOps Auto](file:///c:/Users/savya/projects/agentic_os/agentos_core/devops_auto)**: Automated CI/CD, PR management, and deployment orchestration.
- **[Productivity](file:///c:/Users/savya/projects/agentic_os/agentos_core/productivity)**: Personal task management, daily briefings, and workspace knowledge integration.

## Data Flow (Internal)

1. **Request**: Received via WebSocket or HTTP gatekeeper.
2. **Plan**: ReAct loop determines the next action.
3. **Queue**: Action is converted into a `Command` and pushed to a specific `Lane`.
4. **Execute**: `LaneRunner` dispatches the command to the `Sandbox` with a signed JWT.
5. **Observe**: Result is returned to the loop for the next reasoning step.

---

## Further Reading

- [Global System Architecture](../../docs/architecture.md)
- [Project Boundaries (ADR-003)](../../docs/adr/003-internal-external-project-boundaries.md)
- [DevOps Documentation](../devops_auto/README.md)
- [Productivity Documentation](../productivity/README.md)
