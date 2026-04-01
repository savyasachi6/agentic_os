# RL Router: Multi-Objective Contextual Bandit

## Overview

The **RL Router** (`rl_router/`) is an RL-based retrieval strategy selector. It is implemented as both:

1. **A standalone microservice** (`rl_router/server.py`) — a FastAPI app with `/predict` and `/reward` endpoints, deployed as its own Docker container.
2. **An embedded in-process bandit** — `CognitiveRetriever` imports the `LinUCBBandit` directly via `rl_router/domain/bandit.py` and calls it synchronously during retrieval. This is the **currently active integration path**.

### Integration Status

> [!IMPORTANT]
> The standalone microservice HTTP endpoints (`/predict`, `/reward`) are **NOT currently called** by `coordinator.py` or `CognitiveRetriever`. The bandit is loaded in-process via `rl_router.api.dependencies.get_bandit()` with a fallback to `LinUCBBandit(n_arms=8, d=7)`. The HTTP service exists for future out-of-process wire-up.

---

## Contextual Bandit Architecture (`rl_router/domain/bandit.py`)

A thread-safe **LinUCB Contextual Bandit** with exponential decay and CUSUM drift detection.

### Action Space — 8 Retrieval Arms

Defined in `agent_core/rag/retrieval_policy.py:RetrievalArm`:

| Arm | Name | `k` | Hybrid | Notes |
| :--- | :--- | :--- | :--- | :--- |
| 0 | ShallowSemantic | 5 | No | Default low-cost arm |
| 1 | DeepSemantic | 12 | No | Deeper memory + skills |
| 2 | ShallowHybrid | 8 | Yes | Broadened candidate pool |
| 3 | DeepHybrid | 20 | Yes | Most comprehensive |
| 4 | MetaFiltered | 8 | Yes | Metadata pre-filter |
| 5 | SQLFallback | 10 | Yes | SQL + chunk fallback |
| 6 | ParentChild | 5 | Yes | Recursive context expansion |
| 7 | RecencyBiased | 10 | No | Exponential recency bias |

### Context Features (`agent_core/rag/retrieval_policy.py:map_intent_to_context`)

The context vector fed to the bandit has **dimension 9**:

| Features | Count | Description |
|---|---|---|
| Intent one-hot | 5 | `RESEARCH`, `TECHNICAL`, `CAPABILITY`, `ACTION`, `GENERAL` |
| `q_len_norm` | 1 | Query word count / 50, clamped to [0,1] |
| `c_len_norm` | 1 | Query char count / 300, clamped to [0,1] |
| `s_depth_norm` | 1 | Session turn count / 10, clamped to [0,1] |
| `entropy_norm` | 1 | Query word entropy / 8, clamped to [0,1] |

### Reward Signal (`agent_core/rag/retrieval_policy.py:calculate_retrieval_reward`)

Multi-objective weighted reward:

$$R = 0.40 \cdot accepted + 0.20 \cdot no\_fallback + 0.20 \cdot has\_citation + 0.10 \cdot latency\_score + 0.10 \cdot no\_hallucination$$

Where `latency_score = max(0, 1 - latency_ms / 2000)`.

### Non-Stationarity & Drift (`rl_router/domain/drift.py`)

- **Exponential Decay** (`tau = 0.995`): Gradually fades old covariance history to adapt to evolving usage patterns.
- **CUSUM Drift Detector**: Detects sudden shifts in reward distribution. On detection, triggers a **Soft Reset** — reinitializes the arm's covariance matrix to a fraction of the identity.

### Refinement Policy — `π₂` (`rl_router/domain/refinement.py`)

Acts as an escalation safeguard over the base routing policy (`π₁`):

- **Accept**: Retrieve is valid, proceed.
- **Escalate Depth**: High disagreement in drafted answers → deeper retrieval arm fallback.
- **Abort**: Critical auditor flag → force task cancellation.

---

## Full Feature Vector (Standalone Service) (`rl_router/domain/features.py`)

The standalone service uses a **17-dimensional linguistic feature vector** (inspired by QueryBandits literature):

- *Syntax/Structure*: Interrogative, subordinate clauses, multi-sentence, length, enumerations, negations.
- *Semantics/Domain*: Domain vocabulary, named entities, numeric content, code syntax, temporal references.
- *Pragmatics*: Constraints, comparisons, anaphora, ambiguity.
- *Meta*: Multi-hop required, hypothetical phrasing.

This richer feature set is used by the standalone service's `/predict` endpoint and is not currently active in the embedded bandit path (which uses the 9-d vector from `map_intent_to_context`).

---

## Integration Roadmap

To wire the standalone RL Router service into the production dispatch path, the following integration points are needed:

1. **Pre-dispatch (Coordinator)**: Before calling a specialist, `coordinator.py` should POST the query and context to `http://rl_router:8001/predict` to get `(arm_index, depth, speculative)`.
2. **Post-response (Coordinator)**: After the specialist completes, POST the reward signal to `http://rl_router:8001/reward` using the `rl_metadata` collected in `last_run_metrics`.

Until then, the bandit runs embedded inside `CognitiveRetriever` with the 9-d feature vector.

> Last updated: arc_change branch — verified against source

