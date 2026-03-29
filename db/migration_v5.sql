-- migration_v5.sql
-- Add 'session_id' to 'nodes' table for denormalization and efficient agent access.

BEGIN;

-- 1. Add the column
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS session_id VARCHAR(255);

-- 2. Index for faster session-based lookups (common for UI/Telemetry)
CREATE INDEX IF NOT EXISTS idx_nodes_session ON nodes (session_id);

-- 3. Backfill data from 'chains' table
UPDATE nodes n
SET session_id = c.session_id
FROM chains c
WHERE n.chain_id = c.id
AND n.session_id IS NULL;

-- 4. Mark column as NOT NULL after backfill (optional, but safer for consistency)
-- ALTER TABLE nodes ALTER COLUMN session_id SET NOT NULL;

COMMIT;
