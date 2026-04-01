# RL Router: Multi-Objective Contextual Bandit

## Overview

The **RL Router** (`rl_router`) is an independent, local-first service responsible for dynamic RAG depth routing. While the *LLM Router* proxies and batches core reasoning requests, the *RL Router* decides the optimal retrieval strategy for a given user query using a reinforcement learning contextual bandit (LinUCB).

### Integration Status
> [!IMPORTANT]
> The `rl_router` service is fully implemented (`bandit.py`, `reward.py`, `drift.py`, `features.py`) but is **NOT currently called** by `coordinator.py` or `CognitiveRetriever`. It runs as a standalone microservice awaiting final wire-up.


## Contextual Bandit Architecture

The router uses a Thread-Safe **LinUCB Contextual Bandit** with safety constraint tracking and exponential decay, integrated with CUSUM drift detection.

The bandit explores an 8-arm action space representing combinations of **Retrieval Depth** and **Speculative Drafting**:

| Arm Index | Retrieval Depth | Speculative Drafting |
| :--- | :--- | :--- |
| 0 | 0 (Collapsed) | OFF |
| 1 | 0 (Collapsed) | ON |
| 2 | 1 (Standard) | OFF |
| 3 | 1 (Standard) | ON |
| 4 | 2 (Multi-hop) | OFF |
| 5 | 2 (Multi-hop) | ON |
| 6 | 3 (Fractal) | OFF |
| 7 | 3 (Fractal) | ON |


### 2. Context Features

The context vector fed into the bandit is high-dimensional and relies heavily on a **17-d Linguistic Feature Vector** (inspired by QueryBandits literature) to characterise the query:

- *Syntax/Structure*: Interrogative, subordinate clauses, multiple sentences, length, enumerations, negations.
- *Semantics/Domain*: Domain vocabulary, named entities, numeric content, code syntax, temporal references.
- *Pragmatics*: Constraints, comparisons, anaphora, ambiguity.
- *Meta*: Requires multi-hop, hypothetical phrasing.

Additional numerical context includes *Intent Logits*, *Difficulty Estimates*, and *Session Hallucination Rate*.

### 3. Multi-Objective Reward Vector

The reward signal relies on four distinct gradients computed continuously from auditor feedback:

- `r1` (+): **Quality** - Overall successful retrieval score
- `r2` (-): **Hallucination Penalty** - Heavy strict penalty clamping
- `r3` (-): **Latency Cost** - Logarithmic smoothing of observed latency
- `r4` (-): **Overthinking Penalty** - Penalty for selecting an unnecessarily deep arm when a shallower arm would have sufficed.

These are scalarised into a final utility score before updating the LinUCB matrices.

### 4. Non-stationarity & Concept Drift

Agent OS usage patterns change dynamically. The bandit accommodates this via:

- **Exponential Decay**: Soft decay factor (`tau=0.995`) gradually fades old history.
- **CUSUM Drift Detector**: Discovers sudden shifts in the reward distribution. If drift is detected, the arm undergoes a **Soft Reset**, resetting the covariance matrix to an identity fraction.

### 5. Refinement Policy ($\pi_2$)

Acts as an escalation safeguard over the base routing policy ($\pi_1$):

- **Accept**: The retrieve is valid.
- **Escalate Depth**: High disagreement in drafted answers demands a deeper retrieval strategy fallback.
- **Abort**: Critical auditor flags force session cancellation.

## Integration Roadmap

The following integration points are required to wire the RL Router into the production dispatch path:

1.  **Pre-dispatch (Coordinator)**: Before calling a specialist, the coordinator should POST the query and context to `/rl_router/predict` to get the arm decision `(depth, speculative, arm_index)`.
2.  **Post-response (Coordinator)**: After the specialist finishes, the coordinator should POST the reward signal back to `/rl_router/reward` using the `rl_metadata` already collected in `last_run_metrics`.

> Last updated: arc_change branch
