-- migration_v7.sql
-- Add context_vector for accurate RL episode replay.
-- Dimension 1052 matches the current LinUCB context dim.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE retrieval_episodes 
ADD COLUMN IF NOT EXISTS context_vector VECTOR(1052);

-- Also ensure id uses 16-char hex as repository.py expects
-- (Existing columns are already there, this is just for context)

COMMIT;
