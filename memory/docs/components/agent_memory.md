# Component: Agent Memory (Transactional)

## Responsibility

The `agent_memory` component provides the persistent state layer for the agent. It ensures that every turn in a conversation, every internal "thought," and every tool result is recorded and indexable.

## Key Submodules

### [Schema](file:///c:/Users/savya/projects/agentic_os/memory/agent_memory/schema.sql)

The SQL definition for the appliance memory. Includes tables for `skills`, `thoughts`, `events`, `chains`, and `docs`.

### [Vector Store](file:///c:/Users/savya/projects/agentic_os/memory/agent_memory/vector_store.py)

The primary Python interface for database operations. It abstracts both standard SQL queries and pgvector similarity searches.

### [Models](file:///c:/Users/savya/projects/agentic_os/memory/agent_memory/models.py)

Standardized Pydantic models for representing session data, search results, and agent thoughts.

## Storage Design

- **Local Ollama Embeddings**: Uses `nomic-embed-text` (or equivalent) for local vector generation.
- **pgvector Integration**: Uses the `hnsw` index type for fast similarity searches over millions of chunks.
