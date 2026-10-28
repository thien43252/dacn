"""Builds the configured providers once; tests swap them with `use_chat_model` / `use_embedder`."""

from app.config import get_settings
from app.llm.base import ChatModel, Embedder, LLMError
from app.llm.fake import FakeChatModel, FakeEmbedder

EMBEDDING_DIMENSIONS = 768

_chat: ChatModel | None = None
_embedder: Embedder | None = None

# USD per 1M tokens (input, output). Only Anthropic prices are known here; other providers record tokens only.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
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
            settings.openai_api_key, settings.llm_main_model, settings.llm_small_model, settings.openai_base_url
        )
    if settings.llm_provider == "gemini":
        from app.llm.gemini_provider import GeminiChatModel

        return GeminiChatModel(settings.gemini_api_key, settings.llm_main_model, settings.llm_small_model)
    if settings.llm_provider == "fake":
        return FakeChatModel()
    raise LLMError(f"LLM_PROVIDER không hợp lệ: {settings.llm_provider}")


def build_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_provider == "openai":
        from app.llm.openai_provider import OpenAIEmbedder

        return OpenAIEmbedder(
            settings.openai_api_key, settings.embedding_model, EMBEDDING_DIMENSIONS, settings.openai_base_url
        )
    if settings.embedding_provider == "gemini":
        from app.llm.gemini_provider import GeminiEmbedder

        return GeminiEmbedder(settings.gemini_api_key, settings.embedding_model, EMBEDDING_DIMENSIONS)
    return FakeEmbedder(EMBEDDING_DIMENSIONS)


def get_chat_model() -> ChatModel:
    global _chat
    if _chat is None:
        _chat = build_chat_model()
    return _chat


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = build_embedder()
    return _embedder


def use_chat_model(model: ChatModel | None) -> None:
    global _chat
    _chat = model


def use_embedder(embedder: Embedder | None) -> None:
    global _embedder
    _embedder = embedder
