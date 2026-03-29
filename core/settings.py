import os
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from typing import Dict, Any, List, Optional

logger = logging.getLogger("agentos.settings")


def get_secret(env_path_var: str, fallback_env: str, default: str) -> str:
    """Utility to read secret from /run/secrets/ or env var."""
    secret_path = os.environ.get(env_path_var)
    if secret_path and os.path.isfile(secret_path):
        try:
            with open(secret_path, "r") as f:
                val = f.read().strip()
                logger.info(f"Resolved secret from {secret_path} (len={len(val)})")
                return val
        except Exception as e:
            logger.error(f"Failed to read secret from {secret_path}: {e}")

    fallback = os.environ.get(fallback_env)
    if fallback:
        return fallback

    return default


class DatabaseSettings(BaseSettings):
    host: str = Field(default="postgres")
    port: int = Field(default=5432)
    db: str = Field(default="agent_os")
    user: str = Field(default="agent")
    password: str = Field(default="agent_os_pw")
    pool_size: int = Field(default=10)
    pool_timeout: int = Field(default=30)
    database_url: str = Field(default="")

    @model_validator(mode="after")
    def resolve_secrets(self) -> "DatabaseSettings":
        self.password = get_secret("POSTGRES_PASSWORD_FILE", "POSTGRES_PASSWORD", self.password)
        return self

    class Config:
        env_prefix = "POSTGRES_"


class RedisSettings(BaseSettings):
    host: str = Field(default="redis")
    port: int = Field(default=6379)
    password: str = Field(default="")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0")

    @model_validator(mode="after")
    def resolve_secrets(self) -> "RedisSettings":
        self.password = get_secret("REDIS_PASSWORD_FILE", "REDIS_PASSWORD", self.password)
        return self

    class Config:
        env_prefix = "REDIS_"


class LLMSettings(BaseSettings):
    model: str = Field(default="qwen3-vl:8b")
    embed_model: str = Field(default="mxbai-embed-large")
    ollama_host: str = Field(default="http://host.docker.internal:11434")
    temperature: float = Field(default=0.7)
    max_retries: int = Field(default=3)

    # OpenAI / OpenRouter support
    openai_api_key: Optional[str] = Field(default=None)
    openai_api_base: str = Field(default="https://openrouter.ai/api/v1")
    openai_model: str = Field(default="google/gemini-2.0-flash-001")


class SecuritySettings(BaseSettings):
    jwt_secret: str = Field(default="change-me-immediately")
    jwt_algorithm: str = Field(default="HS256")
    tls_enabled: bool = Field(default=False)
    admin_secret: str = Field(default="change-me-immediately")
    api_token: str = Field(default="change-me-immediately")
    high_risk_keywords: List[str] = [
        "rm ", "sudo", "pip install", "train", "launch",
        "delete", "format", "chmod", "kill", "reboot",
        "drop table", "deploy", "npm install", "apt",
    ]

    @model_validator(mode="after")
    def resolve_secrets(self) -> "SecuritySettings":
        self.jwt_secret = get_secret("JWT_SECRET_FILE", "JWT_SECRET", self.jwt_secret)
        self.admin_secret = get_secret("ADMIN_SECRET_FILE", "ADMIN_SECRET", self.admin_secret)
        return self


class Settings(BaseSettings):
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    llm: LLMSettings = LLMSettings()
    security: SecuritySettings = SecuritySettings()

    log_level: str = "INFO"
    use_mock_llm: bool = False

    # Deprecated alias kept for backward-compat — prefer browser_ws_url
    lightpanda_ws_url: str = Field(default="ws://lightpanda:9222")

    keycloak_url: str = "http://keycloak:8080"
    keycloak_client_id: str = "agent-os"
    keycloak_client_secret: str = "change-me"

    skills_dir: str = "assets/skills/skills"
    chunk_min_tokens: int = 100
    chunk_max_tokens: int = 250
    retrieval_top_k: int = 4

    router_backend: str = "ollama"
    router_batch_size: int = 8
    router_interval_ms: int = 50

    bandit_alpha: float = 0.25
    bandit_arms: int = 8
    bandit_dim: int = 1052

    reward_lambda_h: float = 0.8
    reward_lambda_l: float = 0.1
    reward_gamma: float = 0.15

    sandbox_base_port: int = 9100
    sandbox_timeout: int = 3600
    sandbox_cleanup_delay: int = 60

    max_agent_calls_per_agent: int = 2
    max_total_agent_calls: int = 8
    history_compact_threshold: int = 1000
    cache_ttl_seconds: int = 3600
    embed_dim: int = 1024

    # ── Distributed RL Routing ────────────────────────────────────────────────
    rl_router_url: str = Field(default="http://rl-router:8100")
    # Raised from 5.0 → 15.0 s: the /route endpoint calls the embedding model
    # (mxbai-embed-large) before selecting a bandit arm, which regularly exceeds
    # 5 s on a warm GPU and almost always exceeds it on cold start.
    rl_router_timeout: float = Field(default=15.0)

    # ── Browser (lightpanda) ──────────────────────────────────────────────────
    # Reads BROWSER_WS_URL from the Docker environment (set in docker-compose.yml).
    # Falls back to the lightpanda service hostname on the browser-net network.
    # NOTE: do NOT use validation_alias here — pydantic-settings v2 resolves
    # Field(alias=...) for env lookups automatically when populate_by_name=True.
    browser_ws_url: str = Field(default="ws://lightpanda:9222", alias="BROWSER_WS_URL")

    # ── Web-search API keys (optional) ────────────────────────────────────────
    # Brave Search is optional. If BRAVE_SEARCH_API_KEY is absent, web_search
    # falls back to DuckDuckGo via lightpanda CDP (no key required).
    brave_search_api_key: Optional[str] = Field(
        default_factory=lambda: (
            os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY") or None
        )
    )

    # ── MCP Servers ───────────────────────────────────────────────────────────
    # Only include servers whose npm packages actually exist and whose required
    # credentials are available at runtime.
    #
    # Removed:
    #   - "fetch"  → @modelcontextprotocol/server-fetch does not exist on npm (404)
    #   - "brave"  → requires BRAVE_API_KEY; web search is handled by the Python
    #                WebSearchAction tool (DuckDuckGo fallback via lightpanda CDP)
    mcp_servers: Dict[str, Dict[str, Any]] = {
        "filesystem": {
            "transport": "stdio",
            # Pass /app explicitly so the server is scoped to the container workspace
            "command": "npx -y @modelcontextprotocol/server-filesystem /app",
        },
        "memory": {
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-memory",
        },
        "postgres": {
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-postgres",
            # DATABASE_URL must be set in the container environment (docker-compose.yml)
            "env": {
                "DATABASE_URL": os.environ.get(
                    "DATABASE_URL",
                    "postgresql://agent:agent_os_pw@postgres:5432/agent_os",
                )
            },
        },
        "github": {
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-github",
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_TOKEN", "")
            },
        },
        "puppeteer": {
            "transport": "stdio",
            "command": "npx -y @modelcontextprotocol/server-puppeteer",
        },
    }

    # ── Flat properties for backward-compatibility ────────────────────────────
    @property
    def database_url(self) -> str:
        """Constructs DB URL using resolved password."""
        if self.db.database_url:
            return self.db.database_url
        return f"postgresql://{self.db.user}:{self.db.password}@{self.db.host}:{self.db.port}/{self.db.db}"

    @property
    def redis_url(self) -> str:
        if self.redis.password:
            return f"redis://:{self.redis.password}@{self.redis.host}:{self.redis.port}/0"
        return f"redis://{self.redis.host}:{self.redis.port}/0"

    @property
    def ollama_base_url(self) -> str:
        return self.llm.ollama_host

    @property
    def ollama_model(self) -> str:
        return self.llm.model

    @property
    def openai_api_key(self) -> Optional[str]:
        return self.llm.openai_api_key

    @property
    def openai_base_url(self) -> str:
        return self.llm.openai_api_base

    @property
    def openai_model(self) -> str:
        return self.llm.openai_model

    @property
    def embed_model(self) -> str:
        return self.llm.embed_model

    @property
    def admin_secret(self) -> str:
        return self.security.admin_secret

    @property
    def api_token(self) -> str:
        return self.security.api_token

    @property
    def high_risk_keywords(self) -> List[str]:
        return self.security.high_risk_keywords

    @property
    def db_host(self) -> str:
        return self.db.host

    @property
    def db_port(self) -> int:
        return self.db.port

    @property
    def db_user(self) -> str:
        return self.db.user

    @property
    def db_password(self) -> str:
        return self.db.password

    @property
    def db_name(self) -> str:
        return self.db.db

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        extra = "ignore"
        # Required so that both the field name (browser_ws_url) and its alias
        # (BROWSER_WS_URL) are accepted when constructing the model
        populate_by_name = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

SYSTEM_VERSION = "2.7.1-stable"

PROJECT_LINKS = {
    "GitHub Repository": "https://github.com/savya6/agentic_os",
    "Documentation": "https://github.com/savya6/agentic_os#readme",
    "Architecture Diagram": "https://github.com/savya6/agentic_os/blob/main/docs/architecture.md",
    "Agent Roles": "https://github.com/savya6/agentic_os/blob/main/docs/agent-roles-and-workers.md",
    "Streaming Architecture": "https://github.com/savya6/agentic_os/blob/main/docs/streaming-flow.md",
}


def get_links_markdown() -> str:
    lines = [f"## 🌌 Agentic OS (v{SYSTEM_VERSION})", "### 🔗 Project Links"]
    for name, url in PROJECT_LINKS.items():
        lines.append(f"- **{name}**: {url}")
    return "\n".join(lines)
