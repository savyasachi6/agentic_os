"""
Configuration loader for the Agentic RL Router.
Reads from .env using pydantic-settings.

This is the ONLY module that touches env vars and files.
Domain and application layers receive config values via injection.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path
from typing import Optional


def resolve_secret(env_name: str, default: str = "password") -> str:
    """
    Resolve a configuration value, prioritizing:
    1. ${env_name}_FILE (e.g. POSTGRES_PASSWORD_FILE) pointing to a secret file
    2. /run/secrets/db_password as a global default
    3. secrets/db_password.txt as a local default
    4. ${env_name} environment variable directly
    5. Provided default value
    """
    # 1. Check for secret file (Docker Secrets convention)
    file_path = os.getenv(f"{env_name}_FILE")
    if file_path and os.path.exists(file_path):
        try:
            return Path(file_path).read_text().strip()
        except Exception:
            pass

    # 2. Check for explicit secrets folder mapping as backup
    for alt_path in ["/run/secrets/db_password", "secrets/db_password.txt", f"secrets/{env_name.lower()}.txt"]:
        path = Path(alt_path)
        if path.exists():
            try:
                content = path.read_text().strip()
                if content:
                    return content
            except Exception:
                pass

    # 3. Fallback to standard environment variable
    return os.getenv(env_name, default)


class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    name: str = Field(default="agent_os", validation_alias="POSTGRES_DB")
    user: str = Field(default="agent", validation_alias="POSTGRES_USER")
    password: str = Field(default_factory=lambda: resolve_secret("POSTGRES_PASSWORD"))
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
    context_dim: int = Field(default=1052)
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
