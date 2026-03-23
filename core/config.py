"""
core/config.py
==============
Application settings loaded from environment variables.
All config access goes through this module — never call
os.getenv() directly in agent or tool files.
Raises EnvironmentError at startup if required vars are missing.
"""
import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv

from urllib.parse import urlparse

@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    ollama_base_url: str
    ollama_model: str
    lightpanda_ws_url: str
    log_level: str
    admin_secret: str
    api_token: str
    skills_dir: str
    chunk_min_tokens: int
    chunk_max_tokens: int

    @property
    def db_host(self) -> str:
        return urlparse(self.database_url).hostname or "localhost"

    @property
    def db_port(self) -> int:
        return urlparse(self.database_url).port or 5432

    @property
    def db_user(self) -> str:
        return urlparse(self.database_url).username or "agent"

    @property
    def db_password(self) -> str:
        return urlparse(self.database_url).password or ""

    @property
    def db_name(self) -> str:
        return urlparse(self.database_url).path.lstrip("/") or "agent_os"

def load_settings() -> Settings:
    """Load settings from environment variables with validation."""
    load_dotenv() # Load from .env if present
    
    # Check for direct URL or construct from components
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "agent_os")
        user = os.getenv("POSTGRES_USER", "agent")
        pw = os.getenv("POSTGRES_PASSWORD")
        if pw:
            db_url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"
        elif "PYTEST_CURRENT_TEST" in os.environ or os.getenv("GITHUB_ACTIONS"):
            # Provide a dummy URL for test collection
            db_url = "postgresql://agent:test@localhost:5432/agent_os"
        else:
            db_url = ""

    missing: List[str] = []
    if not db_url:
        missing.append("DATABASE_URL (or POSTGRES_PASSWORD)")
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings(
        database_url     = db_url,
        redis_url        = redis_url,
        ollama_base_url  = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434")),
        ollama_model     = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2")),
        lightpanda_ws_url= os.getenv("LIGHTPANDA_WS_URL", "ws://localhost:9222"),
        log_level        = os.getenv("LOG_LEVEL", "INFO"),
        admin_secret     = os.getenv("ADMIN_SECRET", os.getenv("JWT_SECRET", "change-me-immediately")),
        api_token        = os.getenv("API_TOKEN", "change-me-immediately"),
        skills_dir       = os.getenv("SKILLS_DIR", "skills"),
        chunk_min_tokens = int(os.getenv("CHUNK_MIN_TOKENS", "500")),
        chunk_max_tokens = int(os.getenv("CHUNK_MAX_TOKENS", "800"))
    )
    
    if missing:
        error_msg = (
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Please check your .env file or .env.example."
        )
        raise EnvironmentError(error_msg)
        
    return settings

# Singleton instance for the entire application
settings = load_settings()
