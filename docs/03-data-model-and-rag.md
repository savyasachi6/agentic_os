# Data Model & RAG

## Persistence Layer

Agentic OS relies on **PostgreSQL with the `pgvector` extension** for all semantic and relational storage.

### Core Schema Tables

| Table | Purpose |
|---|---|
| `chains` | One chain per user session. Anchor for all nodes in that session. |
| `nodes` | Execution records — every specialist task is a Node with `PENDING → RUNNING → DONE/FAILED` lifecycle. |
| `thoughts` | Vector-indexed log of all LLM reasoning steps (user and assistant messages). Used by Memory retrieval. |
| `skill_chunks` | Chunked content from indexed skills/documents. Atomic unit of the RAG system. |
| `knowledge_skills` | Skill registry — name, description, embedding, and skill_type metadata. |
| `skill_relations` | Explicit edges between skills, used by the Relational CTE walk. |
| `entity_relations` | Entity-level graph edges (source/target entity type + ID). |
| `retrieval_events` | Telemetry log for each retrieval call (strategy, latency, chunks retrieved). Used to compute bandit rewards. |
| `session_summaries` | LLM-generated compaction summaries triggered when session history exceeds 50 thoughts. |

---

## Cognitive Retrieval Pipeline

**File**: `agent_core/rag/cognitive_retriever.py`

The `CognitiveRetriever` is the single in-process entry point for all retrieval. It replaces the former `HybridRetriever`. It is instantiated once per specialist worker process (stateless except for the shared embedder and bandit).

### Step 1 — Bandit Arm Selection (Strategy Routing)

Before any DB queries, the retriever selects a **retrieval strategy** using an embedded **LinUCB contextual bandit** (`rl_router/domain/bandit.py`, loaded via `rl_router/api/dependencies.py`).

**Feature vector** passed to the bandit (dimension = 9):
- **Intent one-hot** (5 binary features): `RESEARCH`, `TECHNICAL`, `CAPABILITY`, `ACTION`, `GENERAL`
- **Normalized continuous**: query word count, character count, session turn depth, query entropy

**8 retrieval arms** (`agent_core/rag/retrieval_policy.py`):

| Arm | Name | `k` | Hybrid | Notes |
|---|---|---|---|---|
| 0 | ShallowSemantic | 5 | No | Default low-cost arm |
| 1 | DeepSemantic | 12 | No | More memory + skills |
| 2 | ShallowHybrid | 8 | Yes | Candidate-broadened |
| 3 | DeepHybrid | 20 | Yes | Most comprehensive |
| 4 | MetaFiltered | 8 | Yes | Metadata pre-filter |
| 5 | SQLFallback | 10 | Yes | SQL + chunk fallback |
| 6 | ParentChild | 5 | Yes | Recursive context expansion |
| 7 | RecencyBiased | 10 | No | Exponential recency bias |

`override_top_k` (passed by callers) bypasses the bandit-selected `k`.

Fast-exit: if `intent == "web_search"`, `context_k = 0` and retrieval is skipped entirely.

### Step 2 — Query Rewriting

If the session has prior context (fetched from Redis via `A2ABus.get_session_turns`), the retriever calls the LLM at `ModelTier.NANO` to rewrite the query into a self-contained retrieval statement. Short or long queries (>20 words) are passed through unchanged.

### Step 3 — Bifurcated Candidate Generation

`candidate_k = max(context_k × 5, 20)` for hybrid arms — a broad pool for effective RRF reranking.

Retrieval layers run in **parallel** via `asyncio.gather`:

- **M — Memory**: Vector search over `thoughts` table, scoped to the current `session_id`.
- **S — Skills**: `pgvector` cosine search over `knowledge_skills` / `skill_chunks`, with optional `skill_type` filter (e.g., `"code"` for `CODE_GEN` intent).
- **R — Relational**: A recursive SQL CTE walk starting from skill IDs matched in the S layer, traversing `skill_relations` and `entity_relations` up to 2 hops.

### Step 4 — Neighbor Expansion

For each `skill_registry` result, adjacent chunks (±1 window) are fetched from `skill_chunks` in the same skill to provide surrounding context. Neighbors receive a fixed score of `0.35`.

### Step 5 — Session Episode Prefix

Recent `DONE` RAG/research nodes from the current chain are prepended as `[Session History]` context before the RRF results.

### Step 6 — RRF Fusion & Precision Truncation

Results from all layers are combined using **Reciprocal Rank Fusion**:

$$score(d) = \sum_{s \in sources} \frac{1}{60 + rank_s(d)}$$

A **Recency Multiplier** of `1.25×` is applied to chunks whose `skill_name` matches skills referenced in recent session turns.

After RRF, results are truncated to `context_k` to form the final context window.

### Step 7 — Telemetry

After each retrieval, an event is logged to `retrieval_events` via `db.queries.events.log_retrieval_event` — recording `session_id`, `query`, `strategy_name`, `top_k`, `chunk_ids`, and `latency_ms`. This data feeds the bandit reward calculation.

### Multi-Objective Reward Signal (`agent_core/rag/retrieval_policy.py`)

$$R = 0.40 \cdot accepted + 0.20 \cdot no\_fallback + 0.20 \cdot has\_citation + 0.10 \cdot latency\_score + 0.10 \cdot no\_hallucination$$

Where `latency_score = max(0, 1 - latency_ms / 2000)`.

---

## Session History Compaction

When a session accumulates ≥50 `thoughts` AND the delta since the last compaction is ≥20 turns, the RAG worker summarizes the session history using the LLM (`ModelTier.FAST`) and stores the embedding in `session_summaries`. This prevents context overflow in long sessions.

> Last updated: arc_change branch — verified against source

