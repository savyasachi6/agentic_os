import os
import psycopg2
from agent_core.config import settings

def run_sql_script(script_path):
    print(f"Reading from {script_path}")
    with open(script_path, "r", encoding="utf-8") as f:
        sql = f.read()

    db_url = settings.database_url.replace("@postgres:", "@localhost:")
    print(f"Connecting to database at {db_url}…")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
            print("Successfully executed script.")
        conn.close()
    except Exception as e:
        print(f"Error executing script: {e}")

if __name__ == "__main__":
    run_sql_script("db/init/02_skill_relations.sql")
    run_sql_script("db/init/03_seed_skill_graphs.sql")
