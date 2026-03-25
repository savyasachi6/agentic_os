-- migration_v4.sql
-- Final Alignment: 1024-dim parity across all infrastructure.
-- This fixes the "expected 1536, not 1024" error in the RAG Agent.

BEGIN;

-- 1. Align 'semantic_cache'
-- We drop the indexes first, then alter the column type.
DROP INDEX IF EXISTS idx_semantic_cache_hnsw;
DROP INDEX IF EXISTS idx_semantic_cache_hot_hnsw;

-- TRUNCATE as old 1536 embeddings are useless
TRUNCATE TABLE semantic_cache;

ALTER TABLE semantic_cache 
ALTER COLUMN query_vector TYPE vector(1024);

-- Recreate indexes
CREATE INDEX idx_semantic_cache_hnsw ON semantic_cache USING hnsw (query_vector vector_cosine_ops);

-- 2. Align 'nodes'
-- TreeStore nodes often have embeddings for similarity search.
DROP INDEX IF EXISTS idx_nodes_hnsw;

-- We don't truncate 'nodes' as it contains the Task/Chat history!
-- Instead we NULL out old 1536 embeddings.
UPDATE nodes SET embedding = NULL;

ALTER TABLE nodes 
ALTER COLUMN embedding TYPE vector(1024);

-- Recreate index
CREATE INDEX idx_nodes_hnsw ON nodes USING hnsw (embedding vector_cosine_ops);

COMMIT;
