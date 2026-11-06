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
    # Empty means api.openai.com; set only for a proxy that serves the Responses API (the adapter uses /v1/responses).
    openai_base_url: str = ""
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

    # Tracing (app/tracing.py): off unless both keys are set. Empty base URL means Langfuse Cloud (EU); self-hosted
    # or the US region go here, e.g. http://localhost:3000. Sample rate 0–1 is per trace.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""
    langfuse_sample_rate: float = 1.0

    # Class documents are stored here (relative to backend/).
    upload_dir: str = "data/uploads"

    # Agent runtime. "langgraph" is the in-process graph (app/runtime/graph.py); "dify" sends each turn to the
    # self-hosted Dify apps described in specs/001-dify-core-migration/contracts/dify-apps.md. The old engine stays
    # selectable until the comparison run is done (FR-025).
    runtime_engine: Literal["langgraph", "dify"] = "langgraph"
    dify_base_url: str = "http://127.0.0.1:8080"
    dify_triage_key: str = ""
    dify_runner_key: str = ""
    # Same DSL as the runner with content moderation off; certification only, never user chat.
    dify_runner_raw_key: str = ""
    dify_dataset_key: str = ""
    dify_timeout_s: float = 30.0

    # MCP over streamable HTTP at /mcp, called by Dify with this bearer token. The public URL is what Dify's
    # containers use to reach the backend (host.docker.internal on Docker Desktop).
    mcp_token: str = ""
    mcp_public_url: str = "http://host.docker.internal:8001/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
