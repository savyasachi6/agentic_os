"""
Centralized configuration for the Agent OS.
Uses pydantic-settings to load from environment variables and .env files.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    name: str = Field(default="agent_os", alias="POSTGRES_DB")
    user: str = Field(default="agent", alias="POSTGRES_USER")
    password: str = Field(default="password", alias="POSTGRES_PASSWORD")
    min_connections: int = Field(default=1, alias="DB_MIN_CONN")
    max_connections: int = Field(default=10, alias="DB_MAX_CONN")

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class ModelSettings(BaseSettings):
    llm_model: str = Field(default="qwen3-vl:8b", alias="LLM_MODEL")
    embed_model: str = Field(default="qwen:0.5b", alias="EMBED_MODEL")
    embed_dim: int = Field(default=1024, alias="EMBED_DIM")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    fast_model: str = Field(default="qwen:0.5b", alias="FAST_MODEL")
    reasoning_model: str = Field(default="qwen3-vl:8b", alias="REASONING_MODEL")

    model_config = {"env_file": ".env", "extra": "ignore"}


class AgentSettings(BaseSettings):
    skills_dir: str = Field(default="skills", alias="SKILLS_DIR")
    chunk_min_tokens: int = Field(default=500, alias="CHUNK_MIN_TOKENS")
    chunk_max_tokens: int = Field(default=800, alias="CHUNK_MAX_TOKENS")
    retrieval_top_k: int = Field(default=4, alias="RETRIEVAL_TOP_K")
    react_max_iterations: int = Field(default=10, alias="REACT_MAX_ITERATIONS")
    history_compact_threshold: int = Field(default=3000, alias="HISTORY_COMPACT_THRESHOLD")

    model_config = {"env_file": ".env", "extra": "ignore"}


class ServerSettings(BaseSettings):
    host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    port: int = Field(default=8000, alias="SERVER_PORT")

    model_config = {"env_file": ".env", "extra": "ignore"}


class LLMRouterSettings(BaseSettings):
    batch_interval_ms: int = Field(default=50, alias="ROUTER_BATCH_INTERVAL_MS")
    max_batch_size: int = Field(default=8, alias="ROUTER_MAX_BATCH_SIZE")
    backend: str = Field(default="ollama", alias="ROUTER_BACKEND")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    llama_cpp_model_path: str = Field(default="models/qwen2.5-coder-7b-instruct-q4_k_m.gguf", alias="LLAMA_CPP_MODEL_PATH")

    model_config = {"env_file": ".env", "extra": "ignore"}


class SandboxSettings(BaseSettings):
    worker_timeout_seconds: int = Field(default=300, alias="SANDBOX_TIMEOUT")
    max_memory_mb: int = Field(default=512, alias="SANDBOX_MAX_MEMORY_MB")
    max_workers: int = Field(default=4, alias="SANDBOX_MAX_WORKERS")
    worker_base_port: int = Field(default=9100, alias="SANDBOX_BASE_PORT")

    model_config = {"env_file": ".env", "extra": "ignore"}


class SecuritySettings(BaseSettings):
    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=60, alias="JWT_EXPIRY_MINUTES")
    tls_enabled: bool = Field(default=False, alias="TLS_ENABLED")
    certs_dir: str = Field(default="certs", alias="CERTS_DIR")

    model_config = {"env_file": ".env", "extra": "ignore"}


class QueueSettings(BaseSettings):
    use_queue: bool = Field(default=True, alias="USE_QUEUE")
    poll_interval_seconds: float = Field(default=0.5, alias="QUEUE_POLL_INTERVAL")
    max_retries: int = Field(default=3, alias="QUEUE_MAX_RETRIES")
    tool_timeout_seconds: int = Field(default=300, alias="QUEUE_TOOL_TIMEOUT")

    model_config = {"env_file": ".env", "extra": "ignore"}


class DevOpsSettings(BaseSettings):
    telegram_token: Optional[str] = Field(default=None, alias="TELEGRAM_TOKEN")
    slack_webhook_url: Optional[str] = Field(default=None, alias="SLACK_WEBHOOK_URL")
    metrics_poll_interval: int = Field(default=60, alias="METRICS_POLL_INTERVAL")

    model_config = {"env_file": ".env", "extra": "ignore"}


class ProductivitySettings(BaseSettings):
    notes_dir: str = Field(default="notes", alias="NOTES_DIR")
    todo_table: str = Field(default="todos", alias="TODO_TABLE")
    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    calendar_enabled: bool = Field(default=False, alias="CALENDAR_ENABLED")
    todo_due_threshold_hours: int = Field(default=24, alias="TODO_DUE_THRESHOLD_HOURS")
    notes_chunk_size: int = Field(default=512, alias="NOTES_CHUNK_SIZE")

    model_config = {"env_file": ".env", "extra": "ignore"}


# Singleton instances — import these directly
db_settings = DatabaseSettings()
model_settings = ModelSettings()
agent_settings = AgentSettings()
server_settings = ServerSettings()
llm_router_settings = LLMRouterSettings()
sandbox_settings = SandboxSettings()
queue_settings = QueueSettings()
security_settings = SecuritySettings()
devops_settings = DevOpsSettings()
productivity_settings = ProductivitySettings()
