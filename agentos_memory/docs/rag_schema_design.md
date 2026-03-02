# RAG Skill Graph & Storage Schema Design

This document details the production-grade schema for Agent OS RAG, focusing on the relationship between documents, chunks, skills, and entities.

## 1. Entity-Relationship Narrative

The schema is built around a multi-layered knowledge representative model:

1. **Source Layer**: `documents` holds metadata about where data came from (files, specs, web).
2. **Structural Layer**: `chunks` contains the raw and cleaned text segments, maintaining document order (`chunk_index`) and hierarchy (`section_path`).
3. **Vector Layer**: `chunk_embeddings` stores high-dimensional representations for semantic search. Standardized to 768 dimensions.
4. **Semantic Layer**: `knowledge_skills` and `entities` represent the discrete concepts and real-world items extracted from the text.
5. **Graph Layer**: `entity_relations` and `chunk_skills` link everything together, enabling multi-hop reasoning.

## 2. Module Alignment

### Ingestion (`agent_rag/ingestion/`)

- **Worker**: Inserts to `documents`, then splits into `chunks`.
- **Enrichment**: Extracts `knowledge_skills` and `entities`, linking them via `chunk_skills`.
- **Versioning**: `version` fields in `documents` and `chunk_embeddings` handle re-processing without duplicating data.

### Retrieval (`agent_rag/retrieval/`)

- **Hybrid Search**: Uses a combination of `vector_cosine_ops` (HNSW) and `ts_rank_cd` (GIN) scores.
- **Graph Walk**: `traverse_skills` uses recursive CTEs to find related concepts, expanding the retrieval context beyond simple semantic matches.

### Validation (`agent_rag/validation/`)

- **Auditor**: Uses `source_uri` and `section_path` for provenance verification.
- **Audit Feedback**: Stores results in `audit_feedback` to tune retrieval strategies over time.

## 3. High-Performance Indexing

- **HNSW**: Used on all embedding columns for fast ANN search.
- **GIN**: Used for full-text search (`tsvector`) and metadata filtering (`JSONB`).
- **Triggers**: `trg_chunks_tsvector` automatically updates the weighted lexical index on every insert/update.

## 4. Query Patterns

### Hybrid Skill Retrieval

```sql
WITH vector_matches AS (...) 
SELECT ... 
FROM chunks c 
JOIN chunk_skills cs ON c.id = cs.chunk_id 
...
```

### Knowledge Graph Traversal

```sql
WITH RECURSIVE skill_graph AS (...)
SELECT ... FROM skill_graph;
```
