# Agent OS: Global Architecture Blueprint

This document defines the high-level architecture of the Agent OS "Appliance"—a unified environment for local, secure, and multi-agent AI orchestration.

## 1. The Multi-Layered Oven Architecture

Agent OS is structured as a series of nested layers, ensuring separation between the heavy lifting of models and the refined execution of user-facing tasks.

```mermaid
graph TD
    subgraph Layer 3: Application (External Projects)
        P1["devops-copilot"]
        P2["knowledge-orchestrator"]
        P3["llm-lab"]
    end

    subgraph Layer 2: Platform (Subsystems)
        AC["agentos_core"]
        AM["agentos_memory"]
        AS["agentos_skills"]
    end

    subgraph Layer 1: Infrastructure
        O["Ollama / LPX"]
        DB["PostgreSQL + pgvector"]
        S["Sandboxes / Docker"]
    end

    AC --> AM
    AC --> AS
    AS --> AM
    AC --> O
    AM --> DB
    AC --> S
    Layer 3 --> Layer 2
```

## 2. Primary Subsystems

### [agentos_core](../../agentos_core/README.md)

The central "Brain" of the appliance. It manages the ReAct reasoning loops, distributed command queues, and the security boundary for tool execution.

### [agentos_memory](../../agentos_memory/README.md)

The persistence and retrieval layer. It unifies relational storage (Execution Trees) with semantic vector search (RAG) using `pgvector`.

### [agentos_skills](../../agentos_skills/README.md)

The capability manager. It handles document ingestion, "Smart Chunking", and lift-based skill retrieval for the agent engine.

## 3. Internal Domains (The Logic)

Residing primarily within `agentos_core`, these modules represent specialized business logic:

* **Productivity**: Task planning, calendar management, and personal organization.
* **DevOps**: Automated sysadmin tasks, container management, and log auditing.
* **Security**: JWT-based authentication, RBAC, and sandbox isolation monitoring.
* **Voice**: Integration for STT/TTS and natural language audio interfaces.

## 4. Cross-Cutting Concerns

* **Security**: Mandatory JWT authentication for all external API calls. Internal communication is scoped via per-call permission manifests.
* **Persistence First**: Every thought, command result, and state change is logged to the `Execution Tree` in `agentos_memory`.
* **Latency**: All internal service calls prioritize zero-latency local communication (Unix sockets or localhost IPC) to ensure real-time agent responses.
