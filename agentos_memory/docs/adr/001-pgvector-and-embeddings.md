# ADR-001: Use pgvector with HNSW Indexing

**Status:** Accepted  
**Date:** 2026-03-01

## Context

The Agent OS needs vector similarity search for skill retrieval, thought search, and session summary matching. Options considered:

- **pgvector** (PostgreSQL extension) — HNSW or IVFFlat indexing
- **Standalone vector DB** (Pinecone, Weaviate, Qdrant)
- **In-memory FAISS**

## Decision

Use **pgvector** with **HNSW** indexes.

## Rationale

- **Single dependency**: PostgreSQL already needed for structured data (skills, sessions). Adding pgvector keeps everything in one DB.
- **HNSW over IVFFlat**: HNSW provides better recall at low latency without needing periodic re-training of clusters. For our scale (~1K–10K chunks), build time is negligible.
- **Local-first**: No external API calls. Runs entirely in Docker alongside the agent.
- **Production path**: pgvector 0.5+ is battle-tested, supported by major cloud Postgres providers for future scaling.

## Consequences

- Embedding dimension is fixed at schema creation (768 for `nomic-embed-text`). Changing models requires re-embedding.
- No built-in hybrid search (keyword + vector). If needed, add a separate `tsvector` column.

---

# ADR-002: Local Embeddings via Ollama (nomic-embed-text)

**Status:** Accepted  
**Date:** 2026-03-01

## Context

Need an embedding model for skill chunks, thoughts, and queries. Options:

- **OpenAI text-embedding-3** (1536-dim, API call)
- **nomic-embed-text** via Ollama (768-dim, local)
- **all-MiniLM-L6-v2** via sentence-transformers (384-dim, local)

## Decision

Use **nomic-embed-text** via Ollama.

## Rationale

- Runs fully local — no API keys, no network dependency, no cost.
- 768-dim provides good quality/speed tradeoff for our document sizes.
- Ollama is already required for the LLM, so no new infrastructure.
- `nomic-embed-text` benchmarks well on MTEB for retrieval tasks.

## Consequences

- Embedding calls are synchronous and add ~50ms per chunk. Batch indexing is sequential.
- Tied to Ollama's model availability. If Ollama drops the model, we'd switch to sentence-transformers.
