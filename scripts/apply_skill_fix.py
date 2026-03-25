import sys
import os

# Add the project root to sys.path to import rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_db_connection

def apply_sql_fix():
    sql_path = os.path.join(os.path.dirname(__file__), "fix_skill_types.sql")
    if not os.path.exists(sql_path):
        print(f"SQL file not found: {sql_path}")
        return

    with open(sql_path, "r") as f:
        sql = f.read()

    print("Connecting to database to apply skill type reclassification...")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
            print(f"Applied reclassification logic. Rows affected: {cur.rowcount}")

if __name__ == "__main__":
    apply_sql_fix()
