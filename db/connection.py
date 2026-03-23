"""
db/connection.py
================
Database connection pooling and vector registration.
Provides get_db_connection() context manager for all DB operations.
Uses core/config.py for connection parameters and core/logging_config.py for status.
"""
import logging
import os
from contextlib import contextmanager
from typing import Optional, Generator

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from pgvector.psycopg2 import register_vector

from core.config import settings
from core.logging_config import setup_logging

logger = logging.getLogger("agentos.db")

_pool: Optional[SimpleConnectionPool] = None

# psycopg2 errors that indicate a dropped / stale connection
_TRANSIENT_DB_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)

def init_db_pool(
    min_conn: int = 1, 
    max_conn: int = 10,
    host: Optional[str] = None,
    port: Optional[str] = None,
    dbname: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None
):
    """Initialize (or reinitialize) the global connection pool from settings."""
    global _pool
    
    # Use provided values or fall back to settings
    from urllib.parse import urlparse
    u = urlparse(settings.database_url)
    
    host = host or u.hostname or "localhost"
    port = port or u.port or "5432"
    dbname = dbname or u.path.lstrip("/") or "agent_os"
    user = user or u.username or "agent"
    password = password or u.password or ""

    try:
        _pool = SimpleConnectionPool(
            min_conn,
            max_conn,
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
        logger.info("DB pool initialized -> %s:%s/%s", host, port, dbname)
    except Exception as e:
        logger.error("Failed to initialize DB pool: %s", e)
        raise

def get_pool() -> SimpleConnectionPool:
    """Get the connection pool, initializing if necessary."""
    global _pool
    if _pool is None:
        init_db_pool()
    return _pool

def reset_pool():
    """Tear down and rebuild the pool after a fatal connection error."""
    global _pool
    logger.warning("Resetting DB pool due to connection error…")
    try:
        if _pool is not None:
            _pool.closeall()
    except Exception as e:
        logger.error("Failed to close pool: %s", e)
    _pool = None
    init_db_pool()

@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Yields a pgvector-registered connection from the pool.
    Automatically detects stale/broken connections and retries once with a fresh pool.
    """
    pool = get_pool()
    conn = None
    try:
        try:
            conn = pool.getconn()
            # 'pre-ping': issue a cheap query to verify the connection is alive
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            
            try:
                register_vector(conn)
            except psycopg2.ProgrammingError as e:
                if "vector type not found" in str(e):
                    logger.warning("Vector type not found. Extension might be missing.")
                else:
                    raise
            
            yield conn
        except _TRANSIENT_DB_ERRORS as exc:
            logger.warning("Stale connection detected, refreshing pool…")
            if conn:
                pool.putconn(conn, close=True)
                conn = None
            reset_pool()
            # Retry once
            pool = get_pool()
            conn = pool.getconn()
            register_vector(conn)
            yield conn
    finally:
        if conn:
            pool.putconn(conn)

def init_schema(schema_sql_path: str):
    """Run schema SQL to ensure tables exist."""
    if not os.path.exists(schema_sql_path):
        logger.error("Schema file not found: %s", schema_sql_path)
        return

    with open(schema_sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Get a raw connection from the pool, not via the context manager,
    # so we can safely change autocommit outside any transaction.
    pool = get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True  # set autocommit before starting any transaction

        # register pgvector on this connection as well
        try:
            register_vector(conn)
        except psycopg2.ProgrammingError as e:
            if "vector type not found" in str(e):
                logger.warning("Vector type not found. Extension might be missing.")
            else:
                raise

        with conn.cursor() as cur:
            cur.execute(sql)
        logger.info("Schema initialized successfully.")
    except Exception as e:
        logger.warning("Schema initialization warning: %s", e)
    finally:
        # no need to restore autocommit; this conn goes back to pool
        pool.putconn(conn)
