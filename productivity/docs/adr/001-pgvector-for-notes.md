# ADR 001: Reusing pgvector for Personal Knowledge Base

## Status

Accepted

## Context

We need a storage backend for personal notes and to-dos search.

## Decision

We will reuse the existing `pgvector` container and `agent_memory` abstraction instead of introducing a separate database (like SQLite or Chroma).

## Rationale

1. **Consistency**: Reuses the same infrastructure already set up for agent core thoughts and skills.
2. **Efficiency**: Single database connection pool for all agentic OS operations.
3. **Power**: Provides semantic search capabilities for all personal data out of the box.
