# Agentic OS Canonical Package Map

This document defines the canonical directory structure and namespaces for the Agentic OS repository. All new code and imports should follow this map.

## Runtime Packages (Importable Python)

| Namespace | Directory | Description |
|---|---|---|
| `agent_core` | `agent_core/` | Core orchestration, intent, RAG, LLM routing, tools, graph, and base types. **Primary source of truth.** |
| `agent_core.agents.core` | `agent_core/agents/core/` | `CoordinatorAgent`, `BridgeAgent`, `A2ABus`, `AgentWorker`. |
| `agent_core.agents.specialists` | `agent_core/agents/specialists/` | All specialist worker implementations (rag, code, email, planner, executor, capability, productivity). |
| `agent_core.rag` | `agent_core/rag/` | `CognitiveRetriever`, `RetrievalPolicy`, `Embedder`, `VectorStore`, `RAGStore`, `Indexer`. |
| `agent_core.llm` | `agent_core/llm/` | `LLMRouter`, `LLMClient`, `ModelTier`, backends (Ollama/LlamaCPP/OpenAI). |
| `agent_core.intent` | `agent_core/intent/` | `IntentClassifier`, `route_action_to_agent`. |
| `agent_core.graph` | `agent_core/graph/` | LangGraph `coordinator_graph.py`, `AgentState`, graph nodes. |
| `agent_core.tools` | `agent_core/tools/` | `WebSearchAction`, MCP client, shared tool implementations. |
| `agent_core.security` | `agent_core/security/` | Authentication helpers and JWT logic. |
| `db` | `db/` | `TreeStore` (commands), DB models, `connection.py`, queries (thoughts, skills, commands, events). |
| `gateway` | `gateway/` | FastAPI entry point (`gateway/server.py`). Single REST/WebSocket server. |
| `rl_router` | `rl_router/` | **Standalone** RL routing service: `LinUCBBandit`, reward engine, drift detection, API server. |
| `ui` | `ui/` | Streamlit frontend (`ui/app.py`). |
| `productivity` | `productivity/` | Productivity-specific agent tools. |
| `sandbox` | `sandbox/` | Isolated code execution environment. |
| `voice` | `voice/` | Voice-to-text and TTS interfaces. |

## Core Component Canonical Paths

| Component | File | Description |
|---|---|---|
| **CoordinatorAgent** | `agent_core/agents/core/coordinator.py` | LangGraph orchestrator, `BridgeAgent` host, intent → agent dispatch. |
| **BridgeAgent** | `agent_core/agents/core/coordinator.py` | Inner class. TreeStore + A2ABus dispatcher with heartbeat guard. |
| **A2ABus** | `agent_core/agents/core/a2a_bus.py` | Redis pub/sub message bus for task dispatch and thought streaming. |
| **AgentWorker** | `agent_core/agents/core/worker.py` | Base poller class for specialist workers. |
| **CognitiveRetriever** | `agent_core/rag/cognitive_retriever.py` | Bandit-driven MSR retrieval pipeline (Memory + Skills + Relational). |
| **RetrievalPolicy** | `agent_core/rag/retrieval_policy.py` | 8-arm `RetrievalArm` enum, `STRATEGY_MAP`, `map_intent_to_context()`, reward formula. |
| **LLMRouter** | `agent_core/llm/router.py` | Async micro-batching router with backend failover. |
| **LLMClient** | `agent_core/llm/client.py` | Thin agent-facing wrapper around `LLMRouter`. |
| **IntentClassifier** | `agent_core/intent/classifier.py` | `classify_intent()` → `Intent` enum. |
| **CoordinatorGraph** | `agent_core/graph/coordinator_graph.py` | LangGraph `StateGraph` definition and routing logic. |
| **AgentState** | `agent_core/graph/state.py` | Typed `TypedDict` state shared across all LangGraph nodes. |
| **TreeStore** | `db/queries/commands.py` | Async CRUD for chains and nodes. |
| **Gateway Server** | `gateway/server.py` | FastAPI app with WebSocket `/chat` and REST endpoints. |
| **LinUCBBandit** | `rl_router/domain/bandit.py` | Thread-safe LinUCB implementation (standalone, embedded in CognitiveRetriever). |

## Directory Categorization

- **Runtime Packages**: `agent_core`, `db`, `gateway`, `rl_router`, `ui`, `sandbox`, `voice`, `productivity`
- **Support/Infra**: `infra/`, `scripts/`, `prompts/`, `tests/`
- **Agents (Top-level)**: `agents/` — **empty/transitional** directory (subdirectory stubs only). All agent implementations are in `agent_core/agents/specialists/`.

## Deprecated / Migrated

| Deprecated | Canonical Target | Status |
|---|---|---|
| `agentos_core/` | `agent_core/` | **MIGRATED** |
| `agent_rag/` | `agent_core/rag/` | **MIGRATED** |
| `agents/rag_agent.py` | `agent_core/agents/specialists/rag_agent.py` | **MIGRATED** |
| `agents/code_agent.py` | `agent_core/agents/specialists/code_agent.py` | **MIGRATED** |
| `workers/` | Agent `run_forever()` methods + Docker | **EMPTY** (archived) |
| `core/docs/` | `docs/` | **RESOLVED** |
| `HybridRetriever` | `CognitiveRetriever` | **REPLACED** |
| `_DEPTH_POLICY` dict | `RetrievalArm` + `LinUCBBandit` | **REPLACED** |

> Last updated: arc_change branch — verified against source

