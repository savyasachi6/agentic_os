# RL Router: Multi-Objective Contextual Bandit

## Overview

The **RL Router** (`agentic_rl_router`) is an independent, local-first service responsible for dynamic RAG depth routing. While the *LLM Router* proxies and batches core reasoning requests, the *RL Router* decides the optimal retrieval strategy for a given user query using a reinforcement learning contextual bandit (LinUCB).

The objective is to balance retrieve correctness, latency cost, and hallucination risk, adapting to the user's workload over time.

## Contextual Bandit Architecture

The router uses a Thread-Safe **LinUCB Contextual Bandit** with safety constraint tracking and exponential decay, integrated with CUSUM drift detection.

### 1. Action Space (8 Arms)

The bandit explores an 8-arm action space derived from two orthogonal choices:

- **Retrieval Depth** (0, 1, 2, 3)
  - `0`: Collapsed Tree lookup (no retrieval tree traversal)
  - `1`: Standard RAG
  - `2`: Multi-hop GraphRAG
  - `3`: Full Fractal RAG Tree
- **Speculative Drafting** (ON / OFF)

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
