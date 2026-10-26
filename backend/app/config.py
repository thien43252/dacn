from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or the repo-root `.env`."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://eduagent:eduagent@127.0.0.1:5433/eduagent"
    allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    session_cookie_name: str = "eduagent_session"
    session_hours: int = 12
    cookie_secure: bool = False

    # LLM adapter. The small model serves guards, the router and judges; the main model serves agents.
    # Empty model names use the provider's defaults where it has them (Anthropic: claude-opus-5-5 / claude-haiku-5-5).
    llm_provider: Literal["openai", "anthropic", "gemini", "fake"] = "fake"
    llm_main_model: str = ""
    llm_small_model: str = ""
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    embedding_provider: Literal["openai", "gemini", "fake"] = "fake"
    embedding_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # Orchestration. guard_mode "full" runs every guard layer; "prompt_only" keeps only the platform rules in the
    # system prompt and "off" drops those too (the week 11 experiment compares the three). The tool guard is
    # authorization, not a safety filter, and always runs.
    router_mode: Literal["llm", "keyword"] = "llm"
    guard_mode: Literal["full", "prompt_only", "off"] = "full"

    # Certification pipeline: red-team cases sampled per run, benign cases for over-refusal, parallel runs.
    certify_redteam_cases: int = 30
    certify_benign_cases: int = 6
    certify_concurrency: int = 4

    # Class documents are stored here (relative to backend/).
    upload_dir: str = "data/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
