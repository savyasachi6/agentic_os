# Productivity Engine

Personal Knowledge Management (PKM) and Task Planning for Agent OS.

## Purpose

The `productivity` module enables the agent to act as a deeply integrated personal assistant. It merges traditional task management (Todos) with a semantic second-brain (Notes) and automated morning briefings.

## Key Features

- **Semantic Todo Manager**: Prioritized tasks with `pgvector` deduplication and search.
- **Notes PKM**: Markdown-aware ingestion and RAG-based recall for a private knowledge base.
- **Morning Briefing Generator**: Automated daily synthesis of tasks, calendar events, and DevOps alerts.
- **Hierarchical Task Planner**: Decomposes multi-step fuzzy goals into atomic executable actions.

## Target Users

Professionals and power users looking for an AI-native workspace that can proactively manage their schedule and information.

## Setup & Configuration

The module is integrated into `agentos_core`.

### Environmental Settings

```ini
# Configured in .env
METRICS_POLL_INTERVAL=60
TODO_DUE_THRESHOLD_HOURS=24
NOTES_CHUNK_SIZE=512
```

## Basic Usage

```python
from agentos_core.productivity.todo_manager import add_todo

# Add a semantic task
todo = add_todo(
    title="Prepare for the architectural review",
    priority="high",
    due_date="2026-03-05",
    tags=["work", "arch"]
)
```

## Documentation

- [Architecture](docs/architecture.md)
- [API Reference](docs/api.md)
