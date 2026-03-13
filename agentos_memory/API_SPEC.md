# API Specification: Enterprise Fractal RAG

This document defines the REST/GraphQL surface for interacting with the cognitive memory system.

## 1. Document Ingestion

### `POST /v1/ingest`

Ingests a document, performs hierarchical chunking, generates MD5 signatures, and creates vector embeddings.

**Request Payload:**

```json
{
  "source_uri": "s3://knowledge-base/specs/agent-protocol.pdf",
  "source_type": "s3",
  "content": "Full document text...",
  "metadata": {
    "author": "Systems Arch",
    "version": "2.1.0"
  },
  "options": {
    "chunk_size": 1024,
    "overlap": 100,
    "force_reindex": false,
    "engine": "docling"
  }
}
```

**Workflow:**

1. **Idempotency Check:** Verifies `source_uri` in `documents` table.
2. **Parsing Engine Routing:** Automatically routes complex files (PDF, DOCX) to the **Docling** engine for structure preservation.
3. **Deduplication:** Computes MD5 hash for each chunk.
   - System checks `chunks` table for exact `content_hash` match to prevent redundant embedding.
4. **Embedding:** Generates 1024-dim vector using `mxbai-embed-large` via Ollama.
5. **Graph Bridge:** LLM extraction of entities/relations for `chunk_entities`.

---

## 2. Adaptive Retrieval

### `POST /v1/retrieve`

Performs hybrid search using RRF and experience-weighted boosting.

**Request Payload:**

```json
{
  "query": "How do we handle write amplification in HNSW?",
  "session_id": "sess_9988",
  "top_k": 5,
  "options": {
    "min_relevance": 0.7,
    "strategy": "hybrid",
    "use_experience_boost": true
  }
}
```

**SQL Logic Executed:**

```sql
SELECT * FROM hybrid_search(
  query_vec := :embedding,
  query_text := :query,
  match_limit := :top_k
);
```

**Response:**

Returns ranked chunks with `combined_score`, `source_uri`, and `performance_score` context.

---

## 3. Observability & Feedback (RLHF)

### `POST /v1/audit`

Logs auditor/user feedback to partitioned tables to trigger incremental learning.

**Request Payload:**

```json
{
  "retrieval_event_id": "uuid-1234",
  "is_negative": true,
  "quality_score": 0.2,
  "comments": "Retrieved outdated partition logic.",
  "auditor_role": "strategist"
}
```

**System Side-Effects:**

- **Write:** Record to `audit_feedback`.
- **Trigger:** `trg_audit_feedback_stats` captures the insert.
- **Update:** Asynchronously updates `chunk_scores.performance_score` for the retrieved chunks.

---

## 4. Reasoning Trace (Nodes)

### `GET /v1/thoughts/{session_id}`

Retrieves the recursive "Tree of Thought" for a specific agentic turn.

**Response Schema:**

- `fractal_depth`: Integer level of recursion.
- `parent_id`: For reconstructing tree hierarchy.
- `embedding`: Vector for semantic similarity in thought-space.
