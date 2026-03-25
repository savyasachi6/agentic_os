-- =============================================================
-- Migration v4: Parent-Child Hierarchical Indexing
-- =============================================================
-- Adds a nullable self-referencing FK on the chunks table so that
-- each child chunk can point to its parent chunk.
-- Existing rows remain valid (NULL parent_chunk_id = no hierarchy).
-- =============================================================

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS parent_chunk_id UUID
        REFERENCES chunks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_parent_id
    ON chunks (parent_chunk_id)
    WHERE parent_chunk_id IS NOT NULL;

-- =============================================================
-- End of migration v4
-- =============================================================
