# Agentic OS: The System of Systems

Welcome to the root of the **Agentic OS** ecosystem. This repository serves as the coordination hub and entry point for a distributed, modular AI operating system designed for local execution with high concurrency and strong security.

## 🏛️ High-Level Architecture

Agentic OS is structured as a "System of Systems," where specialized services handle distinct responsibilities. This decoupling allows for independent scaling and clear domain boundaries.

### Core Services (Primary Repositories)

1. **[Agent OS Core](agentos_core/)**: The central reasoning and execution engine. Manages ReAct loops, lane-based command queues, and secure tool sandboxing.
2. **[Agent Memory](agentos_memory/)**: The semantic and relational storage layer. Handles `pgvector`-based RAG, entity extraction, and long-term conversation history.
3. **[Agent Skills](agentos_skills/)**: The capability management layer. Indexes and retrieves `SKILL.md` packages that define agent behaviors and tool usage.

### Internal vs. External Boundaries

* **External Surfaces**: The `Core` service exposes the primary WebSocket/API surface for users. `Projects/` represent pre-packaged solutions built on top of the OS.
* **Internal Protocols**: Services communicate via secure internal protocols (gRPC/mTLS). Modules like `devops_auto` and `productivity` are **Internal Domain Modules** housed within the Core to minimize orchestration overhead.

---

## 🚀 Getting Started

1. **Environment Setup**:
    Copy `.env.example` to `.env` and configure your `OLLAMA_URL` and `POSTGRES_URL`.
2. **Orchestration**: Start the full stack via Docker:

    ```bash
    docker-compose up -d
    ```

3. **Connect**: The agent is ready at `ws://localhost:8000/chat`.

## 📜 Design Records

We use ADRs to track major design decisions. See **[docs/adr/](docs/adr/)**.
