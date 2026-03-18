"""
Unified settings for Agentic OS.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List


class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    name: str = Field(default="agent_os", validation_alias="POSTGRES_DB")
    user: str = Field(default="agent", validation_alias="POSTGRES_USER")
    password: str = Field(default="password", validation_alias="POSTGRES_PASSWORD")
    min_connections: int = Field(default=2, validation_alias="DB_MIN_CONN")
    max_connections: int = Field(default=10, validation_alias="DB_MAX_CONN")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class ModelSettings(BaseSettings):
    llm_model: str = Field(default="qwen3-vl:8b", validation_alias="LLM_MODEL")
    embed_model: str = Field(default="mxbai-embed-large", validation_alias="EMBED_MODEL")
    embed_dim: int = Field(default=1024, validation_alias="EMBED_DIM")
    llm_temperature: float = Field(default=0.7, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, validation_alias="LLM_MAX_TOKENS")
    fast_model: str = Field(default="qwen:0.5b", validation_alias="FAST_MODEL")
    reasoning_model: str = Field(default="qwen3-vl:8b", validation_alias="REASONING_MODEL")
    drafter_model: str = Field(default="glm-4.7-9b", validation_alias="DRAFTER_MODEL")
    verifier_model: str = Field(default="qwen3-coder-next", validation_alias="VERIFIER_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class AgentSettings(BaseSettings):
    skills_dir: str = Field(default="skills", validation_alias="SKILLS_DIR")
    chunk_min_tokens: int = Field(default=500, validation_alias="CHUNK_MIN_TOKENS")
    chunk_max_tokens: int = Field(default=800, validation_alias="CHUNK_MAX_TOKENS")
    retrieval_top_k: int = Field(default=4, validation_alias="RETRIEVAL_TOP_K")
    react_max_iterations: int = Field(default=10, validation_alias="REACT_MAX_ITERATIONS")
    history_compact_threshold: int = Field(default=3000, validation_alias="HISTORY_COMPACT_THRESHOLD")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ServerSettings(BaseSettings):
    host: str = Field(default="0.0.0.0", validation_alias="SERVER_HOST")
    port: int = Field(default=8000, validation_alias="SERVER_PORT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class LLMRouterSettings(BaseSettings):
    batch_interval_ms: int = Field(default=50, validation_alias="ROUTER_BATCH_INTERVAL_MS")
    max_batch_size: int = Field(default=8, validation_alias="ROUTER_MAX_BATCH_SIZE")
    backend: str = Field(default="ollama", validation_alias="ROUTER_BACKEND")
    ollama_base_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    llama_cpp_model_path: str = Field(default="models/qwen2.5-coder-7b-instruct-q4_k_m.gguf", validation_alias="LLAMA_CPP_MODEL_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class QueueSettings(BaseSettings):
    use_queue: bool = Field(default=True, validation_alias="USE_QUEUE")
    poll_interval_seconds: float = Field(default=0.5, validation_alias="QUEUE_POLL_INTERVAL")
    max_retries: int = Field(default=3, validation_alias="QUEUE_MAX_RETRIES")
    tool_timeout_seconds: int = Field(default=300, validation_alias="QUEUE_TOOL_TIMEOUT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class RewardSettings(BaseSettings):
    lambda_h: float = Field(default=0.8)
    lambda_l: float = Field(default=0.1)
    gamma: float = Field(default=0.15)
    l0_ms: float = Field(default=250.0)
    kappa: float = Field(default=2.0)
    hallucination_hard_cap: float = Field(default=-0.3)
    model_config = SettingsConfigDict(env_prefix="REWARD_", extra="ignore")


class BanditSettings(BaseSettings):
    alpha: float = Field(default=0.25)
    n_arms: int = Field(default=8)
    context_dim: int = Field(default=1561)
    decay_tau: float = Field(default=0.995)
    violation_penalty_lambda: float = Field(default=0.3)
    model_config = SettingsConfigDict(env_prefix="BANDIT_", extra="ignore")


class DriftSettings(BaseSettings):
    threshold: float = Field(default=5.0)
    drift_sensitivity: float = Field(default=0.05)
    min_samples_before_detection: int = Field(default=30)
    model_config = SettingsConfigDict(env_prefix="DRIFT_", extra="ignore")


class RedisSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    # Default TTL for L0 cache entries (seconds). 0 = no expiry.
    ttl_seconds: int = Field(default=300, validation_alias="REDIS_TTL_SECONDS")
    # Set to false to disable Redis entirely and fall through to Postgres L1/L2
    enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


# Singleton instances
db_settings = DatabaseSettings()
model_settings = ModelSettings()
agent_settings = AgentSettings()
server_settings = ServerSettings()
llm_router_settings = LLMRouterSettings()
queue_settings = QueueSettings()
reward_settings = RewardSettings()
bandit_settings = BanditSettings()
drift_settings = DriftSettings()
redis_settings = RedisSettings()
