"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "backend" / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = f"sqlite:///{ROOT / 'data' / 'wakeful.db'}"
    secret_key: str = "dev-insecure-change-me"  # noqa: S105 - placeholder, overridden by .env
    token_encryption_key: str = ""  # Fernet key; generated per-process in dev if empty
    admin_password: str = ""  # plain (first run convenience) - prefer admin_password_hash
    admin_password_hash: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Fanvue
    fanvue_mode: Literal["mock", "live"] = "mock"
    fanvue_client_id: str = ""
    fanvue_client_secret: str = ""
    fanvue_api_base: str = "https://api.fanvue.com"
    fanvue_auth_base: str = "https://auth.fanvue.com"
    fanvue_api_version: str = "2025-06-26"
    fanvue_scopes: str = (
        "openid offline_access read:self read:chat write:chat read:fan read:insights read:media read:creator"
    )
    fanvue_webhook_secret: str = ""
    fanvue_poll_seconds: int = 60

    # AI
    ai_provider: Literal["mock", "anthropic", "openai"] = "mock"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ai_max_tokens: int = 600
    ai_temperature: float = 0.8
    ai_price_input_per_mtok: float = 3.0
    ai_price_output_per_mtok: float = 15.0
    ai_history_messages: int = 30

    # Worker
    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0
    job_max_attempts: int = 5

    # Retention
    retention_days_messages: int = 365

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def fanvue_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/fanvue/oauth/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
