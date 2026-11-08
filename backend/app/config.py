"""Runtime configuration. Values come from environment variables or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_prefix="SRP_",
        extra="ignore",
    )

    # Storage. SQLite keeps the vertical slice runnable anywhere; the models are
    # plain SQLAlchemy so DATABASE_URL can point at PostgreSQL later.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'platform.db'}"
    data_dir: Path = BACKEND_DIR / "data"

    # Market-data provider adapter. "yahoo_dev" is unlicensed, delayed data for
    # development only; "fixture" is synthetic offline data for tests and demos.
    provider: str = "yahoo_dev"

    # Research agents. Keys may live in .env; they stay server-side.
    # agent_provider: auto | anthropic | gemini. "auto" uses Claude if ANTHROPIC_API_KEY is set,
    # otherwise Gemini if GEMINI_API_KEY is set (Gemini's API has a free tier).
    agent_provider: str = "auto"
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    gemini_model: str = "gemini-3.6-flash"
    # Tried in order when the main model is overloaded or unavailable (comma-separated).
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.8-flash,gemini-3.1-flash-lite"
    agents_enabled: bool = True
    agent_model: str = "claude-opus-5-5"
    agent_effort: str = "medium"
    agent_timeout_seconds: float = 180.0
    agent_max_tokens: int = 16000

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
