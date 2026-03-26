# Agentic OS: The System of Systems

Welcome to the **Agentic OS** ecosystem. This project provides a production-grade, modular AI operating system designed for local execution with high concurrency, strong security, and resilient reasoning.

## 🏛️ Architecture Overview

Agentic OS is structured as a "System of Systems," decoupling core reasoning from memory and capability management.

**End-to-End Flow**: User query → `intent/` classifier → `agent_core` CoordinatorAgent → specialists in `agents/` (RAG, code, planner, executor) → RAG retrieval via `rag/` → optional RL-routed refinement via `rl_router/`.

```mermaid
graph TD
    User([User/Client]) <-->|API/CLI| Core[Agent OS Core]
    
    subgraph "Core Intelligence"
        Core <-->|Intent Classification| IC[Intent Classifier]
        Core <-->|Coordinator Turn| C[CoordinatorAgent]
        C <-->|DAG Execution| P[PlannerAgent]
    end

    subgraph "Agent Registry"
        C <-->|Research| RAG[RAGAgent]
        C <-->|Search| WS[WebSearchAgent]
        C <-->|Execute| EX[ExecutorAgent]
        C <-->|Capabilities| CAP[CapabilityAgentWorker]
        C <-->|Audit| AD[AuditorAgent]
    end

    subgraph "Storage Layer"
        RAG <-->|pgvector| AM[Agent Memory]
        AM <-->|Postgres| DB[(Session DB)]
    end
```

### Main Components

- **[Core & Coordinator](agent_core/)**: The primary entry point and reasoning engine. Handles intent classification and agent routing.
- **[Autonomous Agents](agents/)**: specialized modular agents (RAG, Executor, Planner, Auditor, etc.) each with a strict domain and risk profile.
- **[Agent Memory](agent_memory/)**: The semantic storage layer. Managed `pgvector` RAG, semantic caching, and tree-store persistence.
- **[Database Layer](db/)**: Clean SQL-based command and query interfaces for all system state.
- **[System Prompts](prompts/)**: Standardized system instructions for all active agents.

---

## 🌟 Key Features

- **Intent-Driven Routing**: Microsecond classification of user intent (Capability, RAG, Web, Code, etc.) bypasses unnecessary planning.
- **Adaptive RAG Depth**: Powered by an RL router (`rl_router/` + `rag/retrieval/rl_client.py`), a LinUCB contextual bandit learns which retrieval arm (shallow vs fractal tree) to use based on latency, steps, and tool-call telemetry.
- **Risk-Gated Execution**: LOW risk commands execute directly; HIGH risk commands are blocked for explicit human approval.
- **Resilient RAG**: 3-layer retrieval (Cache -> Vector -> Web Fallback) with a strict "single-search" circuit breaker.
- **Strict Architecture**: Zero-knowledge separation between agents ensures no recursive loops or uncontrolled reasoning depth.
- **Local-First**: Optimized for local inference using Ollama or LlamaCPP backends via the LLM router.

---

## Repository Layout

Organized for clarity and runtime stability:

- **Core Packages**: `agent_core`, `agents`, `gateway`, `intent`, `db`, `llm`, `rag`, `rl_router`, `llm_router`, `lane_queue`, `tools`, `ui`, `productivity`, `sandbox`, `voice`
- **assets/**: Specialist assets (`prompts/`, `skills/`, `training/`)
- **infra/**: DevOps and infrastructure (`docker/`, `devops_auto/`, `.env` templates)
- **dev/**: Development and scripts (`scripts/`, `projects/`, `experiments/`, `tests/`)

For a detailed map, see [docs/repo-layout.md](docs/repo-layout.md).

## Getting Started

1. **Environment Setup**:
   ```bash
   cp .env.example .env
   # Configure LLM_MODEL, OLLAMA_URL, and POSTGRES_URL
   ```

2. **Start Infrastructure**:
   ```bash
   docker-compose up -d
   ```

3. **Run the OS (Backend)**:
   ```bash
   git clone https://github.com/agentic-os/agentic-os.git
   cd agentic-os
   python gateway/main.py serve
   ```

4. **Run the UI (Optional)**:
   ```bash
   python ui/app.py
   ```

---

## 📚 Navigation & Docs

- **[Agent Guidelines](AGENTS.md)**: Coding standards and boundaries for system development.
- **[Database Schema](db/schema.sql)**: The underlying data model for chains, nodes, and memory.
- **[Technical Specification](docs/architecture.md)**: Deep dive into the system-of-systems design.

---

## 🛠️ Development

See [development setup](docs/architecture.md#development-setup) for details on testing, linting, and local debugging.
For a detailed overview of the system structure, see the [Canonical Package Map](docs/canonical-package-map.md).

Always run `pytest` before submitting changes.
