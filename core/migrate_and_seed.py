"""
One-time script to:
1. Fix the semantic_cache VECTOR dim from 1536 → 1024
2. Seed some documents for end-to-end testing
"""
import sys, os
# --- Monorepo Shim ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# --------------------

from agent_memory.db import get_db_connection

def run():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Fix semantic_cache vector dimension (need to recreate with correct dim)
            print("Fixing semantic_cache vector dimension...")
            cur.execute("""
                DO $$
                BEGIN
                    -- Check if the column type needs changing
                    IF EXISTS (
                        SELECT 1 FROM pg_attribute a
                        JOIN pg_class c ON c.oid = a.attrelid
                        WHERE c.relname = 'semantic_cache'
                          AND a.attname = 'query_vector'
                          AND a.atttypmod = 1024
                    ) THEN
                        -- Clear existing data first since we can't cast between vector dims
                        DELETE FROM semantic_cache;
                        ALTER TABLE semantic_cache DROP COLUMN query_vector;
                        ALTER TABLE semantic_cache ADD COLUMN query_vector VECTOR(1536) NOT NULL DEFAULT array_fill(0, ARRAY[1536])::vector(1536);
                        RAISE NOTICE 'Fixed semantic_cache.query_vector to VECTOR(1536)';
                    ELSE
                        RAISE NOTICE 'semantic_cache.query_vector already correct or does not match known bad state';
                    END IF;
                END
                $$;
            """)
            
            # 2. Seed some test documents
            print("Seeding documents table...")
            cur.execute("""
                INSERT INTO documents (source_type, source_uri, title, metadata_json)
                VALUES 
                    ('internal_spec', 'test://doc1', 'Agent Architecture Overview', '{"topic": "architecture"}'),
                    ('internal_spec', 'test://doc2', 'SQL Agent Design', '{"topic": "sql_agent"}'),
                    ('internal_spec', 'test://doc3', 'Coordinator Agent', '{"topic": "coordinator"}'),
                    ('internal_spec', 'test://doc4', 'LLM Router', '{"topic": "llm_router"}'),
                    ('internal_spec', 'test://doc5', 'Fractal Cache', '{"topic": "caching"}')
                ON CONFLICT (source_uri) DO NOTHING;
            """)
            count = cur.rowcount
            print(f"Inserted {count} new document(s).")
            
            # Verify
            cur.execute("SELECT COUNT(*) FROM documents;")
            total = cur.fetchone()[0]
            print(f"Total documents now: {total}")
            
        conn.commit()
    print("Done.")

if __name__ == "__main__":
    run()
