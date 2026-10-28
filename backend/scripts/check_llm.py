"""Checks that the model provider configured in .env works for everything the platform needs.

Usage (from backend/): uv run python -m scripts.check_llm

1. streaming chat on the main tier, 2. a JSON answer on the small tier (guards, router, judges),
3. a function/tool call (agents' tools), 4. embeddings (class documents), only when EMBEDDING_PROVIDER is not fake.
"""

import asyncio
import sys
import time

from app.config import get_settings
from app.llm.base import Completion, LLMError, Message, TextDelta, ToolSpec, complete, complete_json
from app.llm.registry import get_chat_model, get_embedder


async def step(name: str, action) -> bool:
    started = time.perf_counter()
    try:
        detail = await action()
    except LLMError as error:
        print(f"  ✗ {name}: {error}")
        return False
    except Exception as error:  # surface anything the adapter did not translate
        print(f"  ✗ {name}: {type(error).__name__}: {error}")
        return False
    print(f"  ✓ {name} ({int((time.perf_counter() - started) * 1000)} ms): {detail}")
    return True


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    model = get_chat_model()
    print(
        f"provider={settings.llm_provider} base_url={settings.openai_base_url or '-'} "
        f"main={model.model_for('main')} small={model.model_for('small')} embeddings={settings.embedding_provider}"
    )

    async def chat() -> str:
        text, final = "", None
        async for event in model.stream(
            [Message(role="user", content="Chào bạn, trả lời đúng một câu ngắn.")],
            system="Bạn là trợ lý.",
            max_tokens=200,
        ):
            if isinstance(event, TextDelta):
                text += event.text
            elif isinstance(event, Completion):
                final = event
        assert final is not None and text.strip(), "không nhận được chữ nào"
        return f"“{text.strip()[:80]}” · {final.usage.input_tokens}+{final.usage.output_tokens} token"

    async def json_answer() -> str:
        answer, _ = await complete_json(
            model,
            "Tin nhắn: Thì hiện tại hoàn thành dùng khi nào?",
            system='Phân loại môn học. Chỉ trả lời JSON: {"subject": "<môn>"}',
        )
        assert answer, "không có JSON"
        return str(answer)

    async def tool_call() -> str:
        spec = ToolSpec(
            "math_check",
            "Kiểm tra phép tính",
            {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        )
        result = await complete(
            model,
            [Message(role="user", content="Dùng công cụ math_check để tính 12*7.")],
            system="Luôn dùng công cụ khi được yêu cầu.",
            tools=[spec],
            max_tokens=300,
        )
        assert result.message.tool_calls, f"mô hình không gọi tool (trả lời: {result.message.content[:80]})"
        call = result.message.tool_calls[0]
        return f"{call.name}({call.arguments})"

    async def embeddings() -> str:
        vectors = await get_embedder().embed(["phương trình bậc nhất"])
        return f"{len(vectors[0])} chiều"

    results = [
        await step("chat stream (main)", chat),
        await step("JSON (small)", json_answer),
        await step("gọi tool", tool_call),
    ]
    if settings.embedding_provider != "fake":
        results.append(await step("embedding", embeddings))
    else:
        print("  - embedding: EMBEDDING_PROVIDER=fake (RAG dùng embedding giả, vẫn chạy được)")
    print("OK, sẵn sàng." if all(results) else "Có bước lỗi, xem chi tiết ở trên.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
