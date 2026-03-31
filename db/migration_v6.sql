-- migration_v6.sql
-- Synchronize all VECTOR columns and indices to 1024-dim parity.
-- This follows the system-wide upgrade to mxbai-embed-large (1024-dim).

BEGIN;

-- 1. Thoughts Table
DROP INDEX IF EXISTS idx_thoughts_hnsw;
ALTER TABLE thoughts ALTER COLUMN embedding TYPE vector(1024);
UPDATE thoughts SET embedding = NULL; -- Clear incompatible 1536-dim vectors
CREATE INDEX idx_thoughts_hnsw ON thoughts USING hnsw (embedding vector_cosine_ops);

-- 2. Session Summaries Table
DROP INDEX IF EXISTS idx_session_summaries_hnsw;
ALTER TABLE session_summaries ALTER COLUMN embedding TYPE vector(1024);
UPDATE session_summaries SET embedding = NULL;
CREATE INDEX idx_session_summaries_hnsw ON session_summaries USING hnsw (embedding vector_cosine_ops);

-- 3. Skill Chunks Table
DROP INDEX IF EXISTS idx_skill_chunks_hnsw;
ALTER TABLE skill_chunks ALTER COLUMN embedding TYPE vector(1024);
UPDATE skill_chunks SET embedding = NULL;
CREATE INDEX idx_skill_chunks_hnsw ON skill_chunks USING hnsw (embedding vector_cosine_ops);

-- 4. Chunk Embeddings Table (Main RAG)
DROP INDEX IF EXISTS idx_chunk_embeddings_hnsw;
ALTER TABLE chunk_embeddings ALTER COLUMN embedding TYPE vector(1024);
UPDATE chunk_embeddings SET embedding = NULL;
CREATE INDEX idx_chunk_embeddings_hnsw ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);

-- 5. Hybrid Search Scalar Stored Procedure Alignment
-- We drop and recreate with the 1024-dim parameter type.
CREATE OR REPLACE FUNCTION hybrid_search(
    query_vec VECTOR(1024),
    query_text TEXT,
    match_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id UUID,
    content TEXT,
    source_uri VARCHAR(1024),
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH semantic_search AS (
        SELECT 
            c.id, 
            c.document_id, 
            c.raw_text,
            ROW_NUMBER() OVER (ORDER BY ce.embedding <=> query_vec) as rank
        FROM chunks c
        JOIN chunk_embeddings ce ON c.id = ce.chunk_id
        WHERE c.deleted_at IS NULL
        ORDER BY ce.embedding <=> query_vec
        LIMIT match_limit * 2
    ),
    keyword_search AS (
        SELECT 
            c.id, 
            c.document_id, 
            c.raw_text,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.fulltext_weighted, websearch_to_tsquery('english', query_text)) DESC) as rank
        FROM chunks c
        WHERE c.fulltext_weighted @@ websearch_to_tsquery('english', query_text)
          AND c.deleted_at IS NULL
        LIMIT match_limit * 2
    )
    SELECT 
        COALESCE(s.id, k.id) AS chunk_id,
        COALESCE(s.raw_text, k.raw_text) AS content,
        d.source_uri,
    (
            (COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0)) +
            (0.05 * COALESCE(cs.performance_score, 0.0))
        )::FLOAT AS combined_score
    FROM semantic_search s
    FULL OUTER JOIN keyword_search k ON s.id = k.id
    JOIN documents d ON d.id = COALESCE(s.document_id, k.document_id)
    LEFT JOIN chunk_scores cs ON cs.chunk_id = COALESCE(s.id, k.id)
    ORDER BY combined_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql;

COMMIT;
