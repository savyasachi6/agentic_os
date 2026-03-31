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

from pathlib import Path
from urllib.parse import urlparse

def resolve_secret(env_name: str, default: str = "") -> str:
    """
    Resolve a configuration value, prioritizing:
    1. ${env_name}_FILE (e.g. POSTGRES_PASSWORD_FILE) pointing to a secret file
    2. ${env_name} environment variable directly
    3. Provided default value
    """
    # 1. Check for secret file (Docker Secrets convention)
    file_path = os.getenv(f"{env_name}_FILE")
    if file_path and os.path.exists(file_path):
        try:
            return Path(file_path).read_text().strip()
        except Exception:
            pass
            
    # 2. Check for explicit secrets folder mapping as backup
    alt_local = Path(f"secrets/{env_name.lower()}.txt")
    if alt_local.exists():
        try:
            return alt_local.read_text().strip()
        except Exception:
            pass

    # 3. Fallback to standard environment variable
    return os.getenv(env_name, default)

@dataclass(frozen=True)
class Settings:
    # --- Infrastructure ---
    database_url: str
    redis_url: str
    ollama_base_url: str
    ollama_model: str
    ollama_model_nano: str
    ollama_model_fast: str
    ollama_model_full: str
    embed_model: str
    browser_ws_url: str
    log_level: str
    admin_secret: str
    api_token: str
    openrouter_api_key: str
    openrouter_base_url: str
    
    # --- Keycloak ---
    keycloak_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    
    # --- RAG & Skills ---
    skills_dir: str
    chunk_min_tokens: int = 100
    chunk_max_tokens: int = 250
    retrieval_top_k: int = 4
    
    # --- LLM Router ---
    router_backend: str = "ollama"
    router_batch_size: int = 8
    router_interval_ms: int = 50
    
    # --- RL Router (Contextual Bandit) ---
    bandit_alpha: float = 0.25
    bandit_arms: int = 8
    bandit_dim: int = 1052
    
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
    embed_dim: int = 1024
    
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
    
    # Resolve DB password via secret files or env
    pw = resolve_secret("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "agent_os")
    user = os.getenv("POSTGRES_USER", "agent")
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        db_url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    settings = Settings(
        database_url     = db_url,
        redis_url        = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        ollama_base_url  = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434")),
        ollama_model     = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "deepseek/deepseek-r1:free")),
        ollama_model_nano = os.getenv("OLLAMA_MODEL_NANO", "google/gemma-2-9b-it:free"),
        ollama_model_fast = os.getenv("OLLAMA_MODEL_FAST", "meta-llama/llama-3-8b-instruct:free"),
        ollama_model_full = os.getenv("OLLAMA_MODEL_FULL", os.getenv("OLLAMA_MODEL", "deepseek/deepseek-r1:free")),
        embed_model      = os.getenv("EMBED_MODEL", "mxbai-embed-large"),
        browser_ws_url   = os.getenv("BROWSER_WS_URL", os.getenv("LIGHTPANDA_WS_URL", "ws://localhost:9222")),
        log_level        = os.getenv("LOG_LEVEL", "INFO"),
        admin_secret     = resolve_secret("ADMIN_SECRET", "change-me-immediately"),
        api_token        = resolve_secret("API_TOKEN", "change-me-immediately"),
        openrouter_api_key = resolve_secret("OPENROUTER_API_KEY", ""),
        openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        keycloak_url     = os.getenv("KEYCLOAK_URL", "http://keycloak:8080"),
        keycloak_client_id = os.getenv("KEYCLOAK_CLIENT_ID", "agent-os"),
        keycloak_client_secret = resolve_secret("KEYCLOAK_CLIENT_SECRET", "change-me"),
        skills_dir       = os.getenv("SKILLS_DIR", "skills"),
        chunk_min_tokens = int(os.getenv("CHUNK_MIN_TOKENS", "100")),
        chunk_max_tokens = int(os.getenv("CHUNK_MAX_TOKENS", "250")),
        retrieval_top_k  = int(os.getenv("RETRIEVAL_TOP_K", "4")),
        
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

# --- Project Links (Phase 4) ---
PROJECT_LINKS = {
    "GitHub Repository": "https://github.com/savya6/agentic_os",
    "Documentation": "https://github.com/savya6/agentic_os#readme",
    "Architecture Diagram": "https://github.com/savya6/agentic_os/blob/main/docs/architecture.md",
    "Agent Roles": "https://github.com/savya6/agentic_os/blob/main/docs/agent-roles-and-workers.md",
}

def get_links_markdown() -> str:
    """Return project links as a structured markdown list."""
    lines = ["## 🔗 Project Links"]
    for name, url in PROJECT_LINKS.items():
        lines.append(f"- **{name}**: {url}")
    return "\n".join(lines)
