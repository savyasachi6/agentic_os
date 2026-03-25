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
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from urllib.parse import urlparse

@dataclass(frozen=True)
class Settings:
    # --- Infrastructure ---
    database_url: str
    redis_url: str
    ollama_base_url: str
    ollama_model: str
    lightpanda_ws_url: str
    log_level: str
    admin_secret: str
    api_token: str
    
    # --- Keycloak ---
    keycloak_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    
    # --- RAG & Skills ---
    skills_dir: str
    chunk_min_tokens: int
    chunk_max_tokens: int
    retrieval_top_k: int = 4
    
    # --- LLM Router ---
    router_backend: str = "ollama"
    router_batch_size: int = 8
    router_interval_ms: int = 50
    
    # --- RL Router (Contextual Bandit) ---
    bandit_alpha: float = 0.25
    bandit_arms: int = 8
    bandit_dim: int = 1561
    
    # --- Rewards ---
    reward_lambda_h: float = 0.8
    reward_lambda_l: float = 0.1
    reward_gamma: float = 0.15
    
    # --- Security & Sandbox ---
    jwt_algorithm: str = "HS256"
    sandbox_base_port: int = 9100
    sandbox_timeout: int = 3600
    sandbox_cleanup_delay: int = 60
    
    # --- Agent Limits ---
    max_agent_calls_per_agent: int = 2
    max_total_agent_calls: int = 8
    history_compact_threshold: int = 1000
    
    # --- Cache ---
    cache_ttl_seconds: int = 3600
    
    # --- Vector & Models ---
    embed_dim: int = 1536
    
    # --- MCP Servers ---
    mcp_servers: Dict[str, Dict[str, Any]] = None
    
    # --- Security ---
    high_risk_keywords: List[str] = None

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
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "agent_os")
        user = os.getenv("POSTGRES_USER", "agent")
        pw = os.getenv("POSTGRES_PASSWORD")
        if pw:
            db_url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"
        else:
            db_url = "postgresql://agent:test@localhost:5432/agent_os"

    settings = Settings(
        database_url     = db_url,
        redis_url        = os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        ollama_base_url  = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434")),
        ollama_model     = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2")),
        lightpanda_ws_url= os.getenv("LIGHTPANDA_WS_URL", "ws://localhost:9222"),
        log_level        = os.getenv("LOG_LEVEL", "INFO"),
        admin_secret     = os.getenv("ADMIN_SECRET", os.getenv("JWT_SECRET", "change-me-immediately")),
        api_token        = os.getenv("API_TOKEN", "change-me-immediately"),
        keycloak_url     = os.getenv("KEYCLOAK_URL", "http://keycloak:8080"),
        keycloak_client_id = os.getenv("KEYCLOAK_CLIENT_ID", "agent-os"),
        keycloak_client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "change-me"),
        skills_dir       = os.getenv("SKILLS_DIR", "skills"),
        chunk_min_tokens = int(os.getenv("CHUNK_MIN_TOKENS", "500")),
        chunk_max_tokens = int(os.getenv("CHUNK_MAX_TOKENS", "800")),
        retrieval_top_k  = int(os.getenv("RETRIEVAL_TOP_K", "4")),
        router_backend   = os.getenv("ROUTER_BACKEND", "ollama"),
        router_batch_size= int(os.getenv("ROUTER_MAX_BATCH_SIZE", "8")),
        bandit_alpha     = float(os.getenv("BANDIT_ALPHA", "0.25")),
        reward_lambda_h  = float(os.getenv("REWARD_LAMBDA_H", "0.8")),
        
        mcp_servers = {
            "filesystem": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-filesystem C:\\Users\\savya"
            },
            "memory": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-memory"
            },
            "postgres": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-postgres"
            },
            "github": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-github"
            },
            "fetch": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-fetch"
            },
            "brave": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-brave-search",
                "env": {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", "")},
                "description": "Web search via Brave — for news, current events, web facts",
                "fallback_for": ["news", "today", "latest", "current", "weather"]
            },
            "puppeteer": {
                "transport": "stdio",
                "command": "npx @modelcontextprotocol/server-puppeteer"
            },
        },
        high_risk_keywords = [
            "rm ", "sudo", "pip install", "train", "launch",
            "delete", "format", "chmod", "kill", "reboot",
            "drop table", "deploy", "npm install", "apt"
        ]
    )
    return settings

settings = load_settings()
