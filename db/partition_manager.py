import os
import logging
import psycopg
from datetime import datetime

# ============================================================
# CONFIGURATION
# Best practice: Use environment variables for credentials
# ============================================================
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "rag_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("partition_maintenance.log"),
        logging.StreamHandler()
    ]
)

def run_partition_maintenance():
    """
    Connects to PostgreSQL and executes the partition management procedure.
    """
    conn_info = (
        f"dbname={DB_CONFIG['dbname']} "
        f"user={DB_CONFIG['user']} "
        f"password={DB_CONFIG['password']} "
        f"host={DB_CONFIG['host']} "
        f"port={DB_CONFIG['port']}"
    )

    try:
        logging.info("Starting partition maintenance task...")
        
        # Connect to the database
        with psycopg.connect(conn_info, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Call the stored procedure defined in the schema
                logging.info("Calling manage_retrieval_partitions()...")
                cur.execute("CALL manage_retrieval_partitions();")
                
                logging.info("Successfully created partitions for the upcoming month.")

    except psycopg.Error as e:
        logging.error(f"Database error during partition maintenance: {e}")
        # In a production environment, you would trigger an alert/email here
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        logging.info("Maintenance task sequence completed.")

if __name__ == "__main__":
    # Recommended Cron Schedule: 0 0 25 * * (Runs on the 25th of every month)
    # This gives the system a 5-6 day buffer before the new month starts.
    run_partition_maintenance()
