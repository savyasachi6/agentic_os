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
    llm_model: str = Field(default="llama3.2", alias="LLM_MODEL")
    embed_model: str = Field(default="nomic-embed-text", alias="EMBED_MODEL")
    embed_dim: int = Field(default=768, alias="EMBED_DIM")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")

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


class SandboxSettings(BaseSettings):
    worker_timeout_seconds: int = Field(default=300, alias="SANDBOX_TIMEOUT")
    max_memory_mb: int = Field(default=512, alias="SANDBOX_MAX_MEMORY_MB")
    max_workers: int = Field(default=4, alias="SANDBOX_MAX_WORKERS")
    worker_base_port: int = Field(default=9100, alias="SANDBOX_BASE_PORT")

    model_config = {"env_file": ".env", "extra": "ignore"}


class QueueSettings(BaseSettings):
    use_queue: bool = Field(default=True, alias="USE_QUEUE")
    poll_interval_seconds: float = Field(default=0.5, alias="QUEUE_POLL_INTERVAL")
    max_retries: int = Field(default=3, alias="QUEUE_MAX_RETRIES")
    tool_timeout_seconds: int = Field(default=300, alias="QUEUE_TOOL_TIMEOUT")

    model_config = {"env_file": ".env", "extra": "ignore"}


# Singleton instances — import these directly
db_settings = DatabaseSettings()
model_settings = ModelSettings()
agent_settings = AgentSettings()
server_settings = ServerSettings()
sandbox_settings = SandboxSettings()
queue_settings = QueueSettings()
