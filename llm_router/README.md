# LLM Router (`llm_router/`)

Centralized inference scheduler for the Agent OS.

## Purpose

To maximize hardware utilization and minimize request contention by batching and scheduling all LLM calls (Thought, Summary, Embedding) through a single process-level manager.

## Features

- **Micro-Batching**: Merges multiple small requests into single inference calls.
- **Priority Scheduling**: Ensures "Thought" steps have higher priority than background tasks.
- **Model Multiplexing**: Routes requests to the appropriate local or remote model (Ollama, vLLM).

## Usage

```python
from llm_router.router import LLMRouter
router = LLMRouter.get_instance()
router.start()
```

See [ADR-003](../docs/adr/003-centralized-llm-router.md) for the design rationale.
