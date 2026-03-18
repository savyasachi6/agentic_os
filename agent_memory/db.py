"""
Database connection pool and schema initialization for the Agent OS.
Includes automatic reconnect on transient OperationalError (e.g. network
blips, postgres restart) using the same backoff strategy as the LLM backend.
"""

import logging
import os
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from pgvector.psycopg2 import register_vector

from agent_config import db_settings
from agent_core.resilience import retry_sync

logger = logging.getLogger("agentos.db")

_pool: SimpleConnectionPool | None = None

# psycopg2 errors that indicate a dropped / stale connection
_TRANSIENT_DB_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _build_pool() -> SimpleConnectionPool:
    return SimpleConnectionPool(
        db_settings.min_connections,
        db_settings.max_connections,
        host=db_settings.host,
        port=db_settings.port,
        dbname=db_settings.name,
        user=db_settings.user,
        password=db_settings.password,
    )


def init_db_pool():
    """Initialize (or reinitialize) the global connection pool from config."""
    global _pool

    def _try_connect():
        return _build_pool()

    _pool = retry_sync(
        _try_connect,
        max_attempts=10,
        base_delay=1.0,
        cap_delay=30.0,
        retryable_exceptions=_TRANSIENT_DB_ERRORS,
        label="DB.init_pool",
    )
    logger.info("[memory] DB pool initialized → %s:%s/%s", db_settings.host, db_settings.port, db_settings.name)
    print(f"[memory] DB pool initialized → {db_settings.host}:{db_settings.port}/{db_settings.name}")


def _reset_pool():
    """Tear down and rebuild the pool after a fatal connection error."""
    global _pool
    logger.warning("[memory] Resetting DB pool due to connection error…")
    try:
        if _pool is not None:
            _pool.closeall()
    except Exception:
        pass
    _pool = None
    init_db_pool()


def init_schema():
    """Run schema.sql against the database to ensure all tables exist.

    Uses autocommit so that each DDL statement runs in its own implicit
    transaction (required for CREATE EXTENSION outside a transaction block).
    Errors like duplicate extension/type are silently skipped via IF NOT EXISTS.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        sql = f.read()

    conn = None
    if _pool is None:
        init_db_pool()
    conn = _pool.getconn()
    try:
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
        except (psycopg2.errors.DuplicateObject, psycopg2.errors.UniqueViolation) as e:
            logger.warning("[memory] Schema already partially applied, skipping: %s", e)
        finally:
            conn.autocommit = old_autocommit
    finally:
        _pool.putconn(conn)

    logger.info("[memory] Schema initialized.")
    print("[memory] Schema initialized.")


@contextmanager
def get_db_connection():
    """
    Yields a pgvector-registered connection from the pool.
    Automatically detects stale/broken connections and retries with a fresh
    pool — the same pattern used by SQLAlchemy's pool 'pre-ping' feature.
    """
    global _pool
    if _pool is None:
        init_db_pool()

    for attempt in range(3):
        conn = _pool.getconn()
        try:
            # 'pre-ping': issue a cheap query to verify the connection is alive
            conn.cursor().execute("SELECT 1")
            try:
                register_vector(conn)
            except psycopg2.ProgrammingError as e:
                if "vector type not found" in str(e):
                    logger.warning("[memory] Vector type not found. This is expected if the extension is not yet created.")
                else:
                    raise
            yield conn
            return
        except _TRANSIENT_DB_ERRORS as exc:
            logger.warning(
                "[memory] Stale connection detected (attempt %d/3): %s — refreshing pool…",
                attempt + 1, exc,
            )
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            _reset_pool()
        finally:
            try:
                _pool.putconn(conn)
            except Exception:
                pass

    raise psycopg2.OperationalError("Could not obtain a live DB connection after 3 attempts.")
