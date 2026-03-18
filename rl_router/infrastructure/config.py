"""
Configuration loader for the Agentic RL Router.
Reads from .env using pydantic-settings.

This is the ONLY module that touches env vars and files.
Domain and application layers receive config values via injection.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    name: str = Field(default="agent_os", validation_alias="POSTGRES_DB")
    user: str = Field(default="agent", validation_alias="POSTGRES_USER")
    password: str = Field(default="password", validation_alias="POSTGRES_PASSWORD")
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


# ---------------------------------------------------------------------------
# Singletons (used by the infrastructure wiring, NOT by domain)
# ---------------------------------------------------------------------------
db_settings = DatabaseSettings()
reward_settings = RewardSettings()
bandit_settings = BanditSettings()
drift_settings = DriftSettings()
