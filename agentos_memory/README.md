# Enterprise Fractal RAG: High-Performance Agentic Memory

[![Architecture: High-Complexity](https://img.shields.io/badge/Architecture-High--Complexity-blueviolet)](https://github.com/savyasachi6/agentic_os)
[![Database: PostgreSQL+pgvector](https://img.shields.io/badge/Database-PostgreSQL%2Bpgvector-blue)](https://github.com/savyasachi6/agentic_os)
[![Search: Hybrid+RRF](https://img.shields.io/badge/Search-Hybrid%2BRRF-green)](https://github.com/savyasachi6/agentic_os)

Enterprise Fractal RAG is a sophisticated cognitive memory architecture designed for high-cardinality agentic workloads. Unlike basic RAG implementations, this system prioritizes **adaptive learning**, **reasoning traceability**, and **write-optimized scaling**.

## 🚀 Value Proposition

- **Adaptive Memory (RLHF):** Chunks learn their own "value" over time through auditor feedback loops, self-optimizing the retrieval hot path.
- **Reasoning Traceability:** Fractal reasoning logs (Trees of Thought) allow for granular inspection of agent decision-making at any recursion depth.
- **Production Scaling:** Range-partitioned observability tables ensure $O(1)$ data retention and index performance stability at multi-million query scales.
- **High-Fidelity Ingestion (Docling):** Integrated IBM Docling for structure-aware parsing of complex PDFs/DOCX, preserving tables and headers perfectly.
- **Deduplication Engine:** Integrated MD5 content hashing prevents "index drift" and redundant embedding generation for exact duplicates.

---

## 🧬 Schema Anatomy

### 1. High-Throughput Partitioning

We employ **Time-Series Range Partitioning** on the `retrieval_events` and `event_chunks` tables. This strategy is critical for:

- **Partition-Wise Joins:** By aligning partition keys on the time dimension, the Postgres planner joins monthly child tables rather than the entire multi-TB log, drastically reducing CPU overhead.
- **O(1) TTL Maintenance:** Expiring data is a metadata operation (`DROP TABLE partition_name`) rather than a heavy vacuum-inducing `DELETE`.

### 2. Deduplication using MD5

To maintain an efficient index, every chunk is assigned an **MD5** content hash.

- **Duplicate Detection:** During ingestion, we check the `chunks` table for any records with the same `document_id` and `content_hash`. Chunks with identical hashes are skipped during the embedding phase to save compute.

### 3. Decoupled Scoring Layer

To prevent **Write Amplification** on fixed-dimension (1024d) vector indexes (HNSW), we decouple "hot" performance scores into a narrow `chunk_scores` table. This prevents frequent MVCC versioning of the heavy `chunk_embeddings` table.

### 4. High-Fidelity Parsing (Docling)

The system uses **Docling** (by IBM) for the ingestion phase. It transforms complex, unstructured files into clean, structured Markdown while preserving:

- **Tables & Formulas:** Maintained in LLM-readable Markdown format.
- **Semantic Hierarchies:** Chunks respect document boundaries (headers, paragraphs) via a `HybridChunker`.

---

## 🔍 Search Logic: Adaptive Hybrid Retrieval

The system uses a custom `hybrid_search` procedure that blends three distinct signals:

### 1. Semantic Vector Search (ANN)

Uses `pgvector` with **HNSW indexing** (`m=16, ef_construction=128`) for ultra-fast candidate generation in high-dimensional (1024d) space.

### 2. Lexical Keyword Search (BM25)

Utilizes GIN-indexed `tsvector` fields for precise keyword matching, ensuring factual recall where semantic distance might be ambiguous.

### 3. Reciprocal Rank Fusion (RRF)

We merge semantic and keyword ranks using the RRF algorithm with a constant $k=60$:

$$RRF(d) = \sum_{s \in \{vector, lexical\}} \frac{1}{60 + rank(d, s)}$$

### 4. Adaptive Experience Boost

The final score is augmented by an empirical `performance_score` cached from the RLHF loop:

$$FinalScore = RRF(d) + (0.05 \times performance\_score)$$

> [!IMPORTANT]
> **The Matthew Effect Mitigation:** We use a calibrated boost multiplier ($0.05$). This ensures that while "proven" documents are prioritized, they do not suppress fresh, highly relevant context—preventing a feedback loop where the system only regurgitates old information.

---

## 🛠 Maintenance & Ops

The system includes automated DDL management:

- **`manage_retrieval_partitions()`:** A stored procedure for monthly partition pre-scaffolding.
- **`mv_chunk_performance`:** An incrementally refreshable materialized view for long-term analytics.

---

## 🏁 Getting Started

- **Initialize Schema:** Execute `schema.sql`.
- **Configure HNSW:** Ensure `vector` extension is enabled.
- **Tune Planner:** Set `enable_partitionwise_join = on` in `postgresql.conf`.
