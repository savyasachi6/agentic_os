-- ============================================================
-- MIGRATION: LEGACY TO PRODUCTION RAG SCHEMA
-- ============================================================

BEGIN;

-- 1. Rename 'skills' to 'knowledge_skills' if it still exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'skills') THEN
        ALTER TABLE skills RENAME TO knowledge_skills_old;
        -- Note: The new schema has 'normalized_name', 'aliases', etc.
        -- We will manually backfill these in Step 3.
    END IF;
END $$;

-- 2. Migrate legacy 'docs' to 'documents' and 'chunks'
INSERT INTO documents (source_uri, source_type, title, metadata_json)
SELECT DISTINCT source_path, COALESCE(doc_type, 'file'), title, '{}'::jsonb
FROM docs
ON CONFLICT (source_uri) DO NOTHING;

INSERT INTO chunks (document_id, chunk_index, raw_text, heading, llm_tags)
SELECT d.id, 0, docs.content, docs.title, docs.tags
FROM docs
JOIN documents d ON docs.source_path = d.source_uri
ON CONFLICT (document_id, chunk_index) DO NOTHING;

-- 3. Backfill normalized_name for knowledge_skills
UPDATE knowledge_skills 
SET normalized_name = lower(replace(name, ' ', '_'))
WHERE normalized_name IS NULL;

-- 4. Re-calculate Full-Text vectors for migrated chunks
-- (This is handled automatically by the trigger we added if we do an UPDATE)
UPDATE chunks SET clean_text = raw_text WHERE clean_text IS NULL;

COMMIT;

-- [WARNING]
-- This script does not migrate chunk embeddings because vector dimensions 
-- may have changed (e.g. 1536 -> 768). 
-- Run the ingestion worker to re-embed your documentation.
