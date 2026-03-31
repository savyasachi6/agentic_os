-- db/init/05_emergency_april_partitions.sql
-- Emergency partition creation for April 2026 and proc stabilization.

-- 1. Create April 2026 partitions (naming convention yYYYYmMM)
CREATE TABLE IF NOT EXISTS retrieval_events_y2026m04 PARTITION OF retrieval_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS event_chunks_y2026m04 PARTITION OF event_chunks
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

-- 2. Update manage_retrieval_partitions() to use consistent naming (yYYYYmMM)
CREATE OR REPLACE PROCEDURE manage_retrieval_partitions()
LANGUAGE plpgsql AS $$
DECLARE
    next_month TIMESTAMPTZ := date_trunc('month', now() + interval '1 month');
    partition_name_events TEXT;
    partition_name_chunks TEXT;
    suffix TEXT := to_char(next_month, '\"y\"YYYY\"m\"MM');
BEGIN
    partition_name_events := 'retrieval_events_' || suffix;
    partition_name_chunks := 'event_chunks_' || suffix;
    
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF retrieval_events 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name_events, 
        next_month, 
        next_month + interval '1 month'
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF event_chunks 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name_chunks, 
        next_month, 
        next_month + interval '1 month'
    );
END;
$$;
