-- migration_v3.sql
-- Next-Generation Agentic RAG Pipeline: Speculative RAG + Fractal + Shared State
-- Idempotent: safe to run on already-migrated databases.

-- ============================================================
-- 1. Speculative Fractal RAG: Draft Storage
-- ============================================================
CREATE TABLE IF NOT EXISTS rag_drafts (
    id              VARCHAR(64) PRIMARY KEY,
    query_hash      TEXT NOT NULL,
    draft_cluster   INT,
    draft_content   TEXT NOT NULL,
    confidence      FLOAT DEFAULT 0.0,
    chunk_ids       VARCHAR(64)[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_drafts_query ON rag_drafts (query_hash);
CREATE INDEX IF NOT EXISTS idx_rag_drafts_confidence ON rag_drafts (query_hash, confidence DESC);

-- ============================================================
-- 2. Content Dependency Graph (Fractal Cache Staleness)
-- ============================================================
CREATE TABLE IF NOT EXISTS content_deps (
    parent_hash     TEXT NOT NULL,
    child_hash      TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_hash, child_hash)
);

CREATE INDEX IF NOT EXISTS idx_content_deps_parent ON content_deps (parent_hash);

-- ============================================================
-- 3. Fractal extensions on nodes
-- ============================================================
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS fractal_depth INT DEFAULT 0;
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS draft_cluster INT;

-- ============================================================
-- 4. Shared Context and staleness extensions on semantic_cache
-- ============================================================
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS shared_context JSONB;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT TRUE;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS hit_count INT DEFAULT 0;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
