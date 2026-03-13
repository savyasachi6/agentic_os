# Agentic RL Router

An independent, local-first service responsible for dynamic RAG depth routing within the **[Agentic OS](..//README.md)**.

## Purpose

The RL Router balances retrieval correctness, latency, and hallucination risk by selecting the optimal retrieval strategy for a given query using reinforcement learning (LinUCB Contextual Bandit).

## Key Features

- **Contextual Bandit Architecture**: Uses a Thread-Safe LinUCB Bandit with safety constraints.
- **8-Arm Action Space**: Explores combinations of retrieval depth (0-3) and speculative drafting (ON/OFF).
- **Multi-Objective Rewards**: Optimizes for Quality (+), Hallucination Penalty (-), Latency (-), and Overthinking (-).
- **Drift Detection**: Integrated CUSUM detector for handling non-stationary usage patterns.

## Architecture

For detailed specs, see **[docs/06-rl-router.md](../docs/06-rl-router.md)**.

## Implementation

The core logic is located in `agentos_router/`:

- `bandit.py`: LinUCB implementation.
- `drift.py`: CUSUM drift detection.
- `reward.py`: Multi-objective scalarization.

## Testing

Verification is handled via **[tests/](tests/)**. Run with:

```bash
pytest tests/
```
