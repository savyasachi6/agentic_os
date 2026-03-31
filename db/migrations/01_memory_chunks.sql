-- db/migrations/run_indexer.py equivalent or base script
CREATE EXTENSION IF NOT EXISTS vector;

-- MemoryChunks matching SQLAlchemy Schema
CREATE TABLE IF NOT EXISTS memory_chunks (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding VECTOR(1536) NOT NULL
);

-- HNSW Index for Cosine Distance
CREATE INDEX IF NOT EXISTS hnsw_memory_idx ON memory_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
