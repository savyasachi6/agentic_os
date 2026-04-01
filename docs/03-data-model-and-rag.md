# Data Model & RAG

## Persistence Layer

Agentic OS relies on PostgreSQL with the `pgvector` extension for all semantic and relational storage.

### Core Schema

- **`thought`**: A vector-indexed table of agent reasoning steps.
- **`document_chunk`**: The atomic unit of the RAG system, segmented by headers or semantic breaks.
- **`skill`**: Functional instructions and prompt fragments used by the Skills engine.
- **`command`**: Durable execution records for the Lane Queue.

## Cognitive Retrieval Pipeline

Located in `agent_core/rag/cognitive_retriever.py`, the pipeline ensures high-fidelity retrieval using an intent-aware, multi-layered approach.

### 1. Depth Policy (`_DEPTH_POLICY`)
The retriever maps query intent to a specific strategy `(top_k, layers)`:
- `WEB_SEARCH` / `MATH` → `top_k=0` (skip retrieval)
- `CODE_GEN` → `top_k=5`, skills only
- `RAG_LOOKUP` / `CONTENT` → `top_k=10`, all layers
- `COMPLEX_TASK` → `top_k=20`, all layers

Note: `override_top_k` allows the RL router to inject depth dynamically once wired.

### 2. Multi-Layer Retrieval (MSR)
Retrieval is bifurcated into three distinct layers:
- **M (Memory)**: Vector search over past thoughts and observations in the current session.
- **S (Skills)**: `pgvector` search against the `skill_registry`.
- **R (Relational)**: Recursive SQL CTE walk via `skill_relations` and `entity_relations` to find connected knowledge hops.

### 3. RRF Fusion & Reranking
Results from all layers are combined using **Reciprocal Rank Fusion (RRF)**:
$score(d) = \sum_{s \in sources} \frac{1}{k + rank_s(d)}$

A **Recency Multiplier** (1.25x) is applied to chunks from skills or topics referenced recently in the session to ensure temporal relevance.

> Last updated: arc_change branch
