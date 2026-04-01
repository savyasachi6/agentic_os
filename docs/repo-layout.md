# Agentic OS Repository Layout

This document describes the actual on-disk structure of the repository and the purpose of each directory.

## Core Runtime Packages

These directories contain importable Python packages that run the Agentic OS ecosystem.

| Directory | Description |
| :--- | :--- |
| `agent_core/` | **Primary package.** Contains all orchestration, agent logic, LLM routing, RAG, intent classification, tools, and base types. |
| `agent_core/agents/core/` | `CoordinatorAgent`, `BridgeAgent`, `A2ABus`, `AgentWorker`. |
| `agent_core/agents/specialists/` | All specialist workers: `rag_agent.py`, `code_agent.py`, `email_agent.py`, `capability_agent.py`, `planner.py`, `executor.py`, `productivity.py`. |
| `agent_core/rag/` | `CognitiveRetriever`, `Embedder`, `VectorStore`, `RAGStore`, `Indexer`, `RetrievalPolicy`. |
| `agent_core/llm/` | `LLMRouter`, `LLMClient`, `ModelTier`, backends (Ollama, LlamaCPP, OpenAI). |
| `agent_core/graph/` | LangGraph `coordinator_graph.py`, `AgentState`, graph nodes. |
| `agent_core/intent/` | `IntentClassifier`, `route_action_to_agent`. |
| `agent_core/tools/` | `WebSearchAction`, MCP client stub. |
| `agent_core/security/` | JWT auth helpers. |
| `agents/` | **Transitional / empty.** Contains only stub subdirectories (`graph/`, `intent/`, `specialists/`, `tools/`). All implementations live in `agent_core/agents/specialists/`. |
| `gateway/` | FastAPI entry point (`server.py`). WebSocket + REST API for client connections. |
| `db/` | DB models, `TreeStore` (commands), connection pool, query modules (thoughts, skills, events). |
| `rl_router/` | **Standalone** RL routing microservice. `LinUCBBandit`, reward engine, drift detector, FastAPI server. Embedded in `CognitiveRetriever` as an in-process bandit. |
| `ui/` | Streamlit frontend (`app.py`). |
| `productivity/` | Productivity-specific tools. |
| `sandbox/` | Isolated code execution. |
| `voice/` | Voice-to-text / TTS interface. |
| `tools/` | Shared MCP server (C# project stub, not currently integrated). |
| `workers/` | **Empty.** Archived directory — worker startup is handled via each specialist's `run_forever()`. |

> Last updated: arc_change branch — verified against source

---

## Assets

Static files and domain knowledge used by the agents.

| Directory | Description |
| :--- | :--- |
| `prompts/` | Markdown system and instruction prompts for each agent (loaded via `agent_core/prompts.py:load_prompt`). |
| `assets/` | Miscellaneous static assets (images, diagrams). |

---

## Infrastructure

DevOps and deployment configurations.

| Directory | Description |
| :--- | :--- |
| `infra/` | Docker configs, `.env` templates, and infrastructure scripts. |
| `docker-compose.yml` | Top-level Compose file. Runs `agent_core`, `gateway`, `rl_router`, `ui`, Postgres, and Redis. |
| `.env.example` / `.env.docker.example` | Environment variable templates. Copy to `.env` before running. |

---

## Development

| Directory | Description |
| :--- | :--- |
| `scripts/` | Helper scripts (e.g., worker management, DB seeding). |
| `tests/` | Unit and integration test suites. |
| `dev/` | Developer scratch scripts and experiments. |
| `legacy/` | Archived code no longer in active use. |
| `sandbox/` | Also contains scratch/experiment code outside the agent isolation context. |
| `tmp/` | Temporary files (gitignored). |
| `logs/` | Runtime log output (gitignored). |

