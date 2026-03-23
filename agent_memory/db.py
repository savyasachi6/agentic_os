"""
agent_memory/db.py (COMPATIBILITY SHIM)
=======================================
This file exists for backward compatibility during the architecture refactor.
All database connection logic has been moved to: db/connection.py
The shim adapts the new core/config.py to the old DatabaseSettings API.

Do not add new logic here. Import from db.connection directly.
"""
import logging
from typing import Any
from db.connection import (
    init_db_pool as _init_db_pool,
    get_db_connection as _get_db_connection,
    init_schema as _init_schema
)
from core.config import settings

logger = logging.getLogger("agentos.db")

# Mocking db_settings object for the old API
class _OldDbSettingsShim:
    @property
    def host(self) -> str: return settings.db_host
    @property
    def port(self) -> int: return settings.db_port
    @property
    def name(self) -> str: return settings.db_name
    @property
    def user(self) -> str: return settings.db_user
    @property
    def password(self) -> str: return settings.db_password
    @property
    def min_connections(self) -> int: return 2
    @property
    def max_connections(self) -> int: return 10

db_settings = _OldDbSettingsShim()

def init_db_pool():
    """Shim for init_db_pool."""
    _init_db_pool(
        min_conn=db_settings.min_connections,
        max_conn=db_settings.max_connections,
        host=db_settings.host,
        port=str(db_settings.port),
        dbname=db_settings.name,
        user=db_settings.user,
        password=db_settings.password
    )

def init_schema():
    """Shim for init_schema."""
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    _init_schema(schema_path)

def get_db_connection():
    """Shim for get_db_connection."""
    return _get_db_connection()
