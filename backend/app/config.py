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

    # LLM adapter for what runs in the backend rather than in Dify: the certification judge and manifest review,
    # quiz_generator and rubric_grader, parent reports. The small model serves judges; the main model the rest.
    # Empty model names use the provider's defaults where it has them (Anthropic: claude-opus-5-5 / claude-haiku-5-5).
    llm_provider: Literal["openai", "anthropic", "gemini", "fake"] = "fake"
    llm_main_model: str = ""
    llm_small_model: str = ""
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    openai_api_key: str = ""
    # Empty means api.openai.com; set only for a proxy that serves the Responses API (the adapter uses /v1/responses).
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

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

    # Agent runtime: every turn goes to the self-hosted Dify apps described in
    # specs/001-dify-core-migration/contracts/dify-apps.md (guardrails, routing and the agent loop run there).
    runtime_engine: Literal["dify"] = "dify"
    dify_base_url: str = "http://127.0.0.1:8080"
    dify_triage_key: str = ""
    dify_runner_key: str = ""
    # Same DSL as the runner with content moderation off; certification only, never user chat.
    dify_runner_raw_key: str = ""
    dify_dataset_key: str = ""
    # eduagent-review: checks a finished answer against the class policy for students and parents; empty = skipped.
    dify_review_key: str = ""
    # eduagent-planner (feature 002): lập kế hoạch cho đường đầy đủ; empty = every turn takes the fast path.
    dify_planner_key: str = ""
    dify_timeout_s: float = 30.0
    # The models the Dify apps run (Dify does not report them); usage_ledger records and prices usage under these.
    dify_triage_model: str = "gpt-4o-mini"
    dify_runner_model: str = "gpt-4o-mini"

    # MCP over streamable HTTP at /mcp, called by Dify with this bearer token. The public URL is what Dify's
    # containers use to reach the backend (host.docker.internal on Docker Desktop).
    mcp_token: str = ""
    mcp_public_url: str = "http://host.docker.internal:8001/mcp"

    # Multi-step orchestration limits (specs/002-multi-agent-orchestration research R12).
    orch_max_clarify_rounds: int = 1  # lần dừng hỏi lại mỗi lượt (FR-008)
    orch_max_questions: int = 3  # câu hỏi mỗi lần (FR-008)
    orch_max_steps: int = 5  # phần việc mỗi lượt (FR-025)
    orch_max_agents: int = 3  # agent tham gia, tính cả agent chính (FR-025)
    orch_max_replans: int = 1  # lần lập lại kế hoạch (FR-025)
    orch_step_timeout_s: float = 60.0  # mỗi phần việc (FR-026)
    orch_deadline_s: float = 120.0  # cả lượt; chốt an toàn, không phải mục tiêu (FR-025)
    orch_pending_ttl_h: float = 24.0  # câu hỏi đang chờ hết hạn sau (FR-013)
    orch_share_review_timeout_s: float = 20.0  # review nội dung chia sẻ trong handler MCP (FR-049)
    # Registers confirm_probe, a confirmation-only test tool (research R6). Tests and eval only.
    enable_test_tools: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
