# AgentOS Memory & RAG

Durable, queryable, and semantic memory layer for the **[Agentic OS](..//README.md)**. Built on PostgreSQL with `pgvector` for high-performance vector similarity search and a resilient RAG verification system.

## Purpose

The `agentos_memory` repository provides a robust foundation for an agent's long-term memory and knowledge retrieval. It bridges structure-aware document ingestion with LLM-based validation to eliminate hallucinations and ensure contextual consistency.

## Key Features

- **Semantic Memory**: pgvector-based storage for thoughts, session summaries, and skill chunks.
- **Resilient RAG**: High-level reasoning modules (Ingestion, Retrieval, Validation) for a scalable RAG architecture.
- **Self-Compacting History**: Automatic summarization of old conversation turns to manage LLM context.
- **Relational & Vector Search**: Hybrid retrieval synthesizing semantic vector search with lexical and relational graph traversals.
- **Validation Engine**: Explicit safety layer (Gatekeeper, Auditor, Strategist) shield against unchecked LLM outputs.

## Target Users

Developers building complex agentic systems that require a reliable, local-first memory subsystem and a high-fidelity RAG engine.

## Setup & Installation

### Prerequisites

- Python 3.11+
- [Docker](https://www.docker.com/) (for PostgreSQL + pgvector)
- [Ollama](https://ollama.ai/) (for `nomic-embed-text` embeddings)

### Database Setup

Start the PostgreSQL instance with `pgvector` using Docker:

```bash
docker run -d \
  --name pgvector \
  -e POSTGRES_DB=agent_os \
  -e POSTGRES_USER=agent \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  ankane/pgvector
```

### Installation

```bash
git clone <repository-url>
cd agentos_memory
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the root directory:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=agent_os
POSTGRES_USER=agent
POSTGRES_PASSWORD=password
EMBED_MODEL=nomic-embed-text
```

## Basic Usage

### Memory Operations

```python
from agent_memory.vector_store import VectorStore
from agent_memory.db import init_schema

# Initialize Database Schema
init_schema()

vs = VectorStore()

# Log a Thought
vs.log_thought(session_id="session-1", role="assistant", content="I should check if the server is running.")

# Semantic Search
results = vs.search_thoughts("Is the server running?", session_id="session-1")
for r in results:
    print(f"[{r['score']:.2f}] {r['content']}")
```

### RAG Retrieval Example

```python
from agent_rag.retrieval.retriever import HybridRetriever

retriever = HybridRetriever()
context = retriever.retrieve("What are the system requirements for Agent OS?")
print(context)
```

## Internal Documentation

- [Architecture Overview](docs/architecture.md)
- [API Reference](docs/api.md)
- [Architecture Decision Records](docs/adr/)
