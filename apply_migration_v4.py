import psycopg2
import os
import sys

# Hardcoded connection string based on common defaults in the project
# (Host would normally be 'db' in docker, but from host it's 'localhost')
conn_str = "dbname=agent_os user=postgres password=postgres host=localhost"

migration_path = r"c:\Users\savya\projects\agentic_os\agent_memory\migration_v4.sql"

def apply_migration():
    try:
        with open(migration_path, 'r') as f:
            sql = f.read()
        
        print(f"Applying migration from {migration_path}...")
        conn = psycopg2.connect(conn_str)
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
