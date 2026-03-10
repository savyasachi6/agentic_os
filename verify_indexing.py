
import psycopg2
from psycopg2.extras import RealDictCursor
import json

def verify_db():
    conn = psycopg2.connect("host=localhost dbname=agent_os user=agent password=password")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("\n--- Knowledge Skills ---")
            cur.execute("SELECT id, name, normalized_name, path, eval_lift, metadata_json FROM knowledge_skills WHERE name = 'postgres-multi-hop-traversal';")
            skills = cur.fetchall()
            for s in skills:
                print(f"ID: {s['id']}, Name: {s['name']}, path: {s['path']}, lift: {s['eval_lift']}")
                print(f"Metadata: {s['metadata_json']}")
                
                print("\n  --- Chunks for this skill ---")
                cur.execute("SELECT chunk_type, heading, token_count, left(content, 100) as preview FROM skill_chunks WHERE skill_id = %s;", (s['id'],))
                chunks = cur.fetchall()
                for c in chunks:
                    print(f"  [{c['chunk_type']}] {c['heading']} ({c['token_count']} tokens): {c['preview']}...")
    finally:
        conn.close()

if __name__ == "__main__":
    verify_db()
