"""Prompt blocks and queries of the full path (specs/002-multi-agent-orchestration research R4, R8).

A step runs the agent's own system prompt (platform rules, role, class policy) plus STEP_MODE, on a fresh Dify
conversation; the synthesis runs the lead's system prompt plus SYNTHESIS_MODE with the working notes, on the main
conversation. The main conversation's memory therefore holds only the request, the extra information the user gave
and the final answer (FR-031).
"""

from typing import Any

MAX_SYSTEM_PROMPT = 12000
# Working notes share this budget in the synthesis prompt; each note gets floor(NOTES_BUDGET / steps).
NOTES_BUDGET = 6000
NOTE_MAX = 6000

STEP_MODE = """# Chế độ phần việc
Đây là MỘT phần việc nội bộ trong quá trình xử lý nhiều bước, không phải câu trả lời gửi người dùng.
- Chỉ làm đúng phần việc được giao. Viết ghi chú làm việc cho agent chính: ngắn gọn, đủ ý, có số liệu và vị trí trong
  tài liệu nếu có. Không chào hỏi, không hỏi lại người dùng trong câu trả lời.
- Vẫn tuân thủ mọi quy tắc nền tảng và chính sách của lớp ở trên (ví dụ không đưa lời giải hoàn chỉnh cho học sinh khi
  lớp cấm).
- Nếu cần agent khác làm một việc ngoài chuyên môn, cần thông tin chỉ người dùng mới biết, hoặc cần người dùng xác nhận
  trước một việc lớn: gọi công cụ tín hiệu tương ứng (request_help, ask_user, request_confirmation) nếu có, rồi kết
  thúc phần việc với những gì đã có."""

SYNTHESIS_MODE = """# Chế độ tổng hợp
Bạn là agent chính của lượt này. Các agent trong lớp đã làm các phần việc bên dưới; người dùng KHÔNG thấy các ghi chú
này. Hãy viết MỘT câu trả lời cuối cho người dùng:
- Ngắn gọn, trả lời thẳng mục tiêu của yêu cầu; tối đa khoảng 300 từ, trừ khi người dùng yêu cầu chi tiết hoặc yêu cầu
  là tạo nội dung dài (ví dụ đề ôn tập).
- Dùng nội dung của ghi chú nhưng viết lại theo lời của bạn; không chép nguyên văn ghi chú, không nhắc tới "ghi chú"
  hay "phần việc".
- Nếu có giả định, nêu ngắn gọn ở cuối dưới dòng "Giả định:".
- Nếu có phần chưa làm được, nói rõ phần đó chưa làm được.
- Nếu có hành động đã hoặc chưa được thực hiện sau khi xin xác nhận, nói rõ kết quả.
- Giữ nguyên các nguồn tài liệu lớp mà ghi chú đã dẫn."""

UNAVAILABLE = "phần “{title}” không có kết quả"


def _block(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}"


def build_step_query(
    goal: str,
    step: dict[str, Any],
    dependency_notes: list[tuple[str, str]],
    request: str,
) -> str:
    """Goal, the step's task, the notes of the steps it depends on, and the original request (research R4)."""
    parts = [f"Mục tiêu chung: {goal}", f"Phần việc của bạn: {step['task']}"]
    for title, note in dependency_notes:
        parts.append(f"Kết quả của phần “{title}”:\n{note.strip() or UNAVAILABLE.format(title=title)}")
    parts.append(f"Yêu cầu gốc của người dùng:\n{request}")
    return "\n\n".join(parts)


def build_synthesis_query(request: str, answers: list[dict[str, str]] | None = None) -> str:
    """What the main Dify conversation records as the user's turn: the request and, after clarifying questions, the
    questions with the user's answers (FR-031)."""
    if not answers:
        return request
    lines = [f"- {item['question']}: {item['answer']}" for item in answers if item.get("answer")]
    if not lines:
        return request
    return request + "\n\nThông tin bổ sung:\n" + "\n".join(lines)


def build_synthesis_prompt(
    base: str,
    notes: list[dict[str, Any]],
    *,
    assumptions: list[str] | None = None,
    confirmations: list[dict[str, Any]] | None = None,
) -> str:
    """The lead's system prompt plus SYNTHESIS_MODE, the working notes (each cut to its share of NOTES_BUDGET so the
    whole stays within the runner's 12000-character limit), assumptions, unfinished parts and confirmation results.

    `notes`: [{title, agent, status, note}] in plan order; steps that are not done are listed as unfinished."""
    done = [n for n in notes if n.get("status") == "done" and (n.get("note") or "").strip()]
    unfinished = [n for n in notes if n not in done]
    sections = [SYNTHESIS_MODE]
    if unfinished:
        sections.append("# Phần chưa làm được\n" + "\n".join(f"- {n['title']}" for n in unfinished))
    if assumptions:
        sections.append("# Giả định đã dùng\n" + "\n".join(f"- {a}" for a in assumptions))
    if confirmations:
        lines = []
        for item in confirmations:
            outcome = item.get("result") or {}
            if outcome.get("done"):
                lines.append(f"- Đã thực hiện: {item.get('summary', '')} {outcome.get('summary', '')}".strip())
            else:
                lines.append(f"- CHƯA thực hiện ({outcome.get('reason', 'user_rejected')}): {item.get('summary', '')}")
        sections.append("# Hành động cần xác nhận\n" + "\n".join(lines))
    if done:
        # The agent's prompt ends with the class policy, so it is never cut: the notes give way instead.
        fixed = len(base) + sum(len(s) + 2 for s in sections) + 2
        headers = sum(len(f"## {n['title']} ({n['agent']})\n") + 2 for n in done) + len("# Ghi chú làm việc\n")
        room = max(0, MAX_SYSTEM_PROMPT - fixed - headers)
        share = min(NOTES_BUDGET, room) // len(done)
        sections.insert(
            1,
            "# Ghi chú làm việc\n"
            + "\n\n".join(_block(f"{n['title']} ({n['agent']})", (n["note"] or "")[:share]) for n in done),
        )
    return (base + "\n\n" + "\n\n".join(sections))[:MAX_SYSTEM_PROMPT]
