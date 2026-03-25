import psycopg2
import os
import sys

# DATABASE_URL: postgresql://user:password@host:port/dbname
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agent_os")
MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "db", "migration_v4.sql")

def apply_migration():
    try:
        if not os.path.exists(MIGRATION_PATH):
            print(f"Error: Migration file not found at {MIGRATION_PATH}")
            return
            
        with open(MIGRATION_PATH, 'r') as f:
            sql = f.read()
        
        print(f"Applying migration from {MIGRATION_PATH}...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        cur.close()
        conn.close()
        print("Migration applied successfully!")
    except Exception as e:
        print(f"Error applying migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    apply_migration()
