# agent_rag

The `agent_rag` subsystem provides the high-level reasoning modules for the Agent OS Scalable RAG System Architecture, built atop the `agent_memory` database layer. It bridges structure-aware document ingestion with LLM-based validation engineering to eliminate hallucinations before they reach the user.

## Architecture & Responsibilities

This repository is divided logically into three components extracted from the [Scalable RAG System Architecture](https://github.com/savyasachi6/relational_connectional_rag):

1. **Ingestion (`agent_rag/ingestion/worker.py`)**:
   Transforms raw documents through `Parsers` and `Structure-Aware Chunking`, adding contextual summaries via `LLM Enrichment` before committing them to the Postgres `RagStore`.
2. **Retrieval (`agent_rag/retrieval/retriever.py`)**:
   The business logic managing `HybridRetriever`, which synthesizes semantic vector searches `<=>` with lexical full-text searches and 1-hop relational graph traversals.
3. **Validation Engine (`agent_rag/validation/agents.py`)**:
   The explicit RAG safety layer shielding end-users from unchecked LLM output:
   * **Gatekeeper**: Validates the initial user query structure.
   * **Auditor**: Fact-checks generated draft answers against the retrieved `Chunks`, returning iterative feedback.
   * **Strategist**: Routes and formats the final validated payload.

## Database Integration

This subsystem is logic-only. It relies fundamentally on the data access patterns established in `agent_memory` (`rag_store.py`) which manages the core `chunks`, `chunk_embeddings`, and `entity_relations` raw schemas in `psycopg2`.
