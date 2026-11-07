"""Builds the configured chat provider once; tests swap it with `use_chat_model`."""

from app.config import get_settings
from app.llm.base import ChatModel, LLMError
from app.llm.fake import FakeChatModel
from app.tracing import TracedChatModel, get_langfuse

_chat: ChatModel | None = None

# USD per 1M tokens (input, output). Only Anthropic prices are known here; other providers record tokens only.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    # The model the Dify apps in infra/dify/ use; the unit prices Dify itself reports in message_end.
    "gpt-4o-mini": (0.15, 0.60),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 6)


def build_chat_model() -> ChatModel:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicChatModel

        return AnthropicChatModel(
            settings.anthropic_api_key, settings.llm_main_model, settings.llm_small_model, settings.llm_effort
        )
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIChatModel

        return OpenAIChatModel(
            settings.openai_api_key,
            settings.llm_main_model,
            settings.llm_small_model,
            settings.openai_base_url,
            settings.llm_effort,
        )
    if settings.llm_provider == "gemini":
        from app.llm.gemini_provider import GeminiChatModel

        return GeminiChatModel(
            settings.gemini_api_key, settings.llm_main_model, settings.llm_small_model, settings.llm_effort
        )
    if settings.llm_provider == "fake":
        return FakeChatModel()
    raise LLMError(f"LLM_PROVIDER không hợp lệ: {settings.llm_provider}")


def get_chat_model() -> ChatModel:
    global _chat
    if _chat is None:
        _chat = TracedChatModel(build_chat_model()) if get_langfuse() else build_chat_model()
    return _chat


def use_chat_model(model: ChatModel | None) -> None:
    global _chat
    _chat = model
