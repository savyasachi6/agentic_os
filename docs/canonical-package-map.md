# Agentic OS Canonical Package Map

This document defines the canonical directory structure and namespaces for the Agentic OS repository. All new code and imports should follow this map. Deprecated directories will be migrated and removed.

## Canonical Namespaces

| Namespace | Directory | Description |
|---|---|---|
| `agent_core` | `agent_core/` | Core orchestration, ReAct loops, and base agent logic. |
| `rag` | `rag/` | Retrieval Augmented Generation components (indexing, retrieval, etc.). |
| `agent_memory` | `agent_memory/` | System-wide memory and state management. |
| `agent_skills` | `agent_skills/` | Tooling and skill implementations. |
| `productivity` | `productivity/` | Productivity-enhancing tools and agents. |
| `sandbox` | `sandbox/` | Secure code execution environments. |
| `voice` | `voice/` | Voice interaction and processing. |
| `gateway` | `gateway/` | System entry points (CLI, API Server). |
| `rl_router` | `rl_router/` | Standalone RL-based routing service (`domain/bandit.py`). |
| `llm_router` | `llm_router/` | Large Language Model-based routing and load balancing. |
| `lane_queue` | `lane_queue/` | Task queue management. |
| `ui` | `ui/` | Streamlit and other user interfaces. |

## Core Component Mappings

| Component | Canonical Path | Description |
|---|---|---|
| **CognitiveRetriever** | `agent_core/rag/cognitive_retriever.py` | Primary retrieval entry point (MSR + RRF). |
| **CoordinatorAgent** | `agent_core/agents/core/coordinator.py` | LangGraph orchestrator and `BridgeAgent` host. |
| **Browser Tools** | `sandbox/browser_tools.py` | Playwright-based `web_search` and `web_fetch`. |
| **Bandit Engine** | `rl_router/domain/bandit.py` | LinUCB implementation (standalone/disconnected). |

> Last updated: arc_change branch


## Deprecation & Migration Map

| Deprecated Directory | Canonical Target | Status |
|---|---|---|
| `agentos_core/` | `agent_core/` | **MIGRATED** |
| `agent_rag/` | `rag/` | **MIGRATED** |
| `core/` (referenced in docs) | `agent_core/` | **RESOLVED** |

## Directory Categorization

- **Runtime Packages**: Directories listed in `pyproject.toml` `[tool.setuptools.packages.find]`.
- **Support Folders**: `McpServer`, `scripts`, `projects`, `prompts`, `tests`, `db`, `tools`, `training`.
- **Models & Checkpoints**: `models`, `checkpoints`.
- **Infrastructure**: `devops_auto`, `.venv`, `.vscode`.
