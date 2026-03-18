# Data Model & RAG

## Persistence Layer

Agentic OS relies on PostgreSQL with the `pgvector` extension for all semantic and relational storage.

### Core Schema

- **`thought`**: A vector-indexed table of agent reasoning steps.
- **`document_chunk`**: The atomic unit of the RAG system, segmented by headers or semantic breaks.
- **`skill`**: Functional instructions and prompt fragments used by the Skills engine.
- **`command`**: Durable execution records for the Lane Queue.

## The Resilient RAG Pipeline

Located primarily in `memory/agent_rag/`, the pipeline ensures high-fidelity retrieval.

### 1. Ingestion

Documents are ingested, cleaned of noise, and chunked using the `skills` indexer logic. Embeddings are generated using local models like `nomic-embed-text`.

### 2. Hybrid Retrieval

A combination of:

- **Vector Search**: Semantic similarity via `pgvector`.
- **Relational Search**: Traversing internal links within documents.
- **Lexical Search**: Traditional keyword matching for exact terms (e.g., error codes).

### 3. Validation

To prevent hallucinations, the **Validation Engine** performs:

- **Fact Checking**: Cross-referencing response claims against the retrieved chunks.
- **Safety Filtering**: Ensuring the output follows system instructions.
