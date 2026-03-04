# AgentOS Skills Management

Skill discovery, chunking, and semantic context orchestration for the **[Agentic OS](..//README.md)**. This component transforms reasoning recipes (Upskill packages) into structured knowledge for the agent loop.

## Purpose

The `agentos_skills` project defines how an agent learns and retrieves specialized capabilities. It manages the lifecycle of "Skills"—structured Markdown documents (`SKILL.md`) that contain instructions, examples, and logic—and provides a high-performance retrieval engine for context injection.

## Key Features

- **Markdown-Aware Chunking**: Intelligently segments documentation by headers (H2/H3) to maintain semantic integrity.
- **Auto-Discovery**: Recursively scans directories to identify and index new skill packages.
- **Lift-Based Re-ranking**: Prioritizes skills based on `eval_lift` (a metric of accuracy improvement) and semantic similarity.
- **Upsert Indexing**: Idempotent indexing ensures the vector store is always in sync with local file changes.
- **Prompt Orchestration**: Formats retrieved skill fragments into token-efficient system prompt context.

## Target Users

Developers and prompt engineers creating complex, specialized agent workflows that require modular, versioned, and searchable "reasoning skills".

## Setup & Installation

### Prerequisites

- Python 3.11+
- **agentos_memory** (must be set up and running for vector storage)

### Installation

```bash
git clone <repository-url>
cd agentos_skills
pip install -r requirements.txt
```

### Configuration

Ensure your `.env` file (managed by `agentos_core` or shared) specifies the `SKILLS_DIR`.

```env
SKILLS_DIR=skills
EMBED_MODEL=nomic-embed-text
```

## Basic Usage

### Indexing Skills

Scan the default `skills/` directory and index all payloads into pgvector:

```python
from agent_skills.indexer import SkillIndexer

indexer = SkillIndexer()
indexer.index_all()
```

### Retrieving Relevant Skills for a Query

```python
from agent_skills.retriever import SkillRetriever

retriever = SkillRetriever()
# session_summary is optional but improves retrieval relevance
context = retriever.retrieve_context("How do I tune PPO hyperparameters?")
print(context)
```

## Internal Documentation

- [Architecture Overview](docs/architecture.md)
- [API Reference](docs/api.md)
- [Architecture Decision Records](docs/adr/)
