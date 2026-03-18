"""
Database connection management.

Provides a connection factory.  In production this would be replaced
with an async pool; for now it mirrors the parent project's psycopg2 pattern.
"""

from __future__ import annotations

import psycopg2

from rl_router.infrastructure.config import db_settings


def get_connection():  # type: ignore[no-untyped-def]
    """Open a fresh psycopg2 connection."""
    return psycopg2.connect(
        host=db_settings.host,
        port=db_settings.port,
        dbname=db_settings.name,
        user=db_settings.user,
        password=db_settings.password,
    )
