-- db/init/04_fix_retrieval_architecture.sql
-- Hardening retrieval isolation and relational graph integrity.

-- 1. Memory Isolation: Add session_id to memory_chunks
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'memory_chunks' AND column_name = 'session_id') THEN
        ALTER TABLE memory_chunks ADD COLUMN session_id VARCHAR(255);
        -- Indexing session_id for fast retrieval & isolation
        CREATE INDEX IF NOT EXISTS idx_memory_chunks_session ON memory_chunks (session_id);
    END IF;
END $$;

-- 2. Performance Tracking: Fix eval_lift defaults if missing
-- Ensure eval_lift has a default for consistent ORDER BY in vector search
-- (This column is in knowledge_skills which is our 'skills' layer)
ALTER TABLE knowledge_skills ALTER COLUMN eval_lift SET DEFAULT 0.0;
UPDATE knowledge_skills SET eval_lift = 0.0 WHERE eval_lift IS NULL;

-- 3. Redundancy Check: Ensure HNSW indexes are active on vectors
CREATE INDEX IF NOT EXISTS idx_memory_chunks_hnsw 
    ON memory_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_skill_chunks_hnsw 
    ON skill_chunks USING hnsw (embedding vector_cosine_ops);
