-- db/create_memory_chunks.sql
-- Alignment with Phase 59 (1024 dimensions)
-- Addresses the 'UndefinedTable' error in the RAG worker logs.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_chunks (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding VECTOR(1024) NOT NULL
);

-- Re-create index utilizing vector_cosine_ops
DROP INDEX IF EXISTS hnsw_memory_idx;
CREATE INDEX IF NOT EXISTS hnsw_memory_idx ON memory_chunks 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

COMMIT;
