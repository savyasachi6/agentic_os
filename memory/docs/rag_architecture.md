# RAG Skill Graph — Storage Architecture

This document provides a technical walkthrough of the production-grade storage schema designed for the `agent_rag` and `agent_memory` subsystems.

## 1. Domain Model

The schema is built on a robust, multi-layered architecture that separates raw content from semantic understanding and audit feedback.

### Layer 1: Content (The Source of Truth)

- **`documents`**: Metadata for logical sources (files, web pages, repositories). Supports versioning, author tracking, and soft deletes.
- **`chunks`**: Structure-aware segments. Stores `raw_text`, `clean_text`, and an MD5 `content_hash` to ensure idempotent ingestion.

### Layer 2: Retrieval (Semantic + Lexical + Cache)

- **`chunk_embeddings`**: Dense vector storage using `pgvector` (`hnsw` index). Built to handle multiple model dimensions and versions.
- **Lexical Search**: Trigger-maintained `fulltext_weighted` TSVECTOR column for high-performance GIN-based keyword search over raw text and summaries.
- **`semantic_cache`**: A high-speed caching layer that intercepts queries. It performs an exact hash match (O(1)) or a fast HNSW semantic vector match, bypassing full retrieval when possible.
- **`hybrid_search`**: A native PostgreSQL stored procedure that implements Reciprocal Rank Fusion (RRF), merging vector similarity and full-text search directly in the database.

### Layer 3: Knowledge Graph (Skills & Entities)

- **`knowledge_skills`**: Canonical registry of discovered capabilities (e.g., "Python", "RL"), normalized for deduplication.
- **`entities`**: General entities (projects, tools, organizations) extracted from text.
- **`chunk_entities`**: A bridge linking chunks to entities/skills with confidence scores.
- **`entity_relations`**: Typed edges (REQUIRES, USES, PART_OF) allowing graph traversal. A `WITH RECURSIVE` CTE query in `rag_store.py` fetches multi-hop relation trees.

### Layer 4: Audit & Optimization

- **`retrieval_events`**: Detailed logs of every search operation (query text, latency, strategy used).
- **`audit_feedback`**: Stores assessments from evaluation agents, directly linking feedback (e.g., hallucination flags, relevance scores) to specific retrieval events and chunks.

## 2. Typical Data Flow

### Ingestion (`worker.py`)

1. **Extraction**: Converts a file into a structured internal representation.
2. **Chunking**: Creates chunks respecting document hierarchy.
3. **Enrichment & Hash**: Calculates an MD5 hash of the text. An LLM extracts summaries, keywords, and specific skills.
4. **Persistence**: `RagStore.upsert_chunks_with_embeddings` skips duplicates automatically using the `content_hash`. Extracted skills are registered and linked in the graph.

### Retrieval & Synthesis (`retriever.py` & `agents.py`)

1. **Planning**: `PlannerAgent` decomposes complex queries into simpler sub-queries.
2. **Retrieval (`ExecutorAgent`)**:
   - Checks the `semantic_cache` first.
   - If miss, executes `RagStore.query_hybrid` using the Postgres stored procedure.
   - Hydrates the result with pre-computed structural 1-hop relations.
   - Saves the result back to the semantic cache.
3. **Execution & Audit**: The `ExecutorAgent` drafts an answer. The `AuditorAgent` validates the output against context, saving its feedback to `audit_feedback`.
4. **Synthesis**: The `OrchestratorAgent` synthesizes sub-answers into a final cohesive response.

## 3. Maintenance and Migration

- **Soft Deletes**: Managed via `deleted_at` timestamps across main entity and text tables.
- **Idempotency**: Reprocessing the same document yields the same `content_hash`, updating metadata without duplicating vectors or graph edges.
- **Cache Invalidation**: The semantic cache tracks staleness versions and can be globally flushed or targeted during major corpus updates.

---
*For API details, see [agent_memory/docs/api.md](../../docs/api.md).*
