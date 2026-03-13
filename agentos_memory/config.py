"""
Configuration loader for AgentOS Memory.
Loads settings from .env file using pydantic-settings.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    name: str = Field(default="agent_os", validation_alias="POSTGRES_DB")
    user: str = Field(default="agent", validation_alias="POSTGRES_USER")
    password: str = Field(default="password", validation_alias="POSTGRES_PASSWORD")
    min_connections: int = 2
    max_connections: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

class ModelSettings(BaseSettings):
    embed_model: str = Field(default="mxbai-embed-large", validation_alias="EMBED_MODEL")
    drafter_model: str = Field(default="glm-4.7-9b", validation_alias="DRAFTER_MODEL")
    verifier_model: str = Field(default="qwen3-coder-next", validation_alias="VERIFIER_MODEL")
    fast_model: str = Field(default="qwen3-coder-next", validation_alias="FAST_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

class DoclingSettings(BaseSettings):
    chunk_size: int = Field(default=1024, validation_alias="DOCLING_CHUNK_SIZE")
    tokenizer: str = Field(default="BAAI/bge-small-en-v1.5", validation_alias="DOCLING_TOKENIZER")
    use_ocr: bool = Field(default=True, validation_alias="DOCLING_USE_OCR")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


db_settings = DatabaseSettings()
model_settings = ModelSettings()
docling_settings = DoclingSettings()
