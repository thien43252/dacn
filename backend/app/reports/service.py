"""Learning activity of a student, aggregated for parents (weekly report), teachers (class progress) and the
`progress_summary` tool.

Reports carry counts and keywords only, never message text: a parent sees that their child asked 12 maths questions,
not what the child wrote. Wellbeing signals (the input guard's "support" verdicts) are reported as a count so the
adult can start a conversation; their content stays in the teacher's audit log.
"""

import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.audit.models import GuardEvent
from app.chat.models import ChatMessage, Conversation
from app.llm.base import ChatModel, LLMError, Usage, complete_json

STOPWORDS = set(
    "là của và có không cho em mình bạn này với được thì một những các trong để về như làm gì nào sao vậy ạ nhé "
    "giúp hãy đi rồi đã sẽ ra vào khi thế nhưng hay hoặc từ theo bài câu ơi cái đó đây nè tôi con cô thầy "
    "giải thích chưa hiểu lại xem thử muốn biết".split()
)
# Placeholders the input guard leaves where personal data was ("[số điện thoại đã ẩn]").
REDACTION = re.compile(r"\[[^\]]*đã ẩn\]")
SUBJECT_NAMES = {
    "toan": "Toán",
    "van": "Ngữ văn",
    "anh": "Tiếng Anh",
    "ly": "Vật lý",
    "hoa": "Hoá học",
    "sinh": "Sinh học",
    "su": "Lịch sử",
    "dia": "Địa lý",
    "gdcd": "GDCD",
    "tin": "Tin học",
}


async def activity(db: AsyncSession, student_id: str, days: int = 7, class_id: str | None = None) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(
            ChatMessage.role, ChatMessage.content, ChatMessage.agent_slug, ChatMessage.status, ChatMessage.created_at
        )
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .where(Conversation.user_id == student_id, Conversation.kind == "chat", ChatMessage.created_at >= since)
    )
    if class_id:
        query = query.where(Conversation.class_id == class_id)
    rows = list(await db.execute(query))
    asked = [row for row in rows if row.role == "user"]
    agents = Counter(row.agent_slug for row in rows if row.role == "assistant" and row.agent_slug)
    keywords = Counter(
        word
        for row in asked
        for word in re.findall(r"[a-zà-ỹđ]{3,}", REDACTION.sub(" ", row.content).lower())
        if word not in STOPWORDS
    )

    subjects: Counter[str] = Counter()
    for slug, count in agents.items():
        agent = await db.scalar(select(Agent).where(Agent.slug == slug))
        for subject in (agent.draft_manifest or {}).get("subjects", []) if agent else []:
            if subject in SUBJECT_NAMES:
                subjects[SUBJECT_NAMES[subject]] += count

    by_day: Counter[date] = Counter(row.created_at.date() for row in asked)
    today = datetime.now(UTC).date()
    events = select(GuardEvent.verdict).where(
        GuardEvent.user_id == student_id, GuardEvent.source == "chat", GuardEvent.created_at >= since
    )
    if class_id:
        events = events.where(GuardEvent.class_id == class_id)
    verdicts = Counter(await db.scalars(events))
    return {
        "period_days": days,
        "questions_asked": len(asked),
        "active_days": len(by_day),
        "daily": [
            {
                "date": (today - timedelta(days=offset)).isoformat(),
                "questions": by_day.get(today - timedelta(days=offset), 0),
            }
            for offset in range(min(days, 14) - 1, -1, -1)
        ],
        "agents_used": dict(agents.most_common(5)),
        "subjects": dict(subjects.most_common(5)),
        "frequent_keywords": [word for word, _ in keywords.most_common(8)],
        "blocked_messages": verdicts.get("block", 0),
        "wellbeing_alerts": verdicts.get("support", 0),
        "last_active": max((row.created_at for row in asked), default=None),
    }


NARRATIVE_SYSTEM = """Bạn viết báo cáo học tập ngắn gửi {audience} về một học sinh trên nền tảng học tập EduAgent Hub.
Chỉ dựa trên số liệu được cung cấp; không bịa điểm số hay nội dung tin nhắn. Giọng ấm áp, cụ thể, tích cực, không phán xét.
Chỉ trả lời JSON: {{"summary": "<2-3 câu>", "highlights": ["<điểm tích cực>", ...], "suggestions": ["<gợi ý cụ thể để {action}>", ...]}}"""


def fallback_narrative(name: str, data: dict[str, Any], audience: str) -> dict[str, Any]:
    """Template report when no model answer is available (offline demo, provider error)."""
    asked, days = data["questions_asked"], data["active_days"]
    if asked == 0:
        summary = f"Trong {data['period_days']} ngày qua, {name} chưa hỏi bài agent nào."
        suggestions = ["Cùng con mở mục “Trợ lý học tập” và thử một câu hỏi về bài đang học."]
    else:
        subjects = ", ".join(data["subjects"]) or "nhiều môn"
        summary = (
            f"Trong {data['period_days']} ngày qua, {name} đã hỏi {asked} câu trong {days} ngày, chủ yếu về {subjects}."
        )
        suggestions = [
            "Hỏi con xem hôm nay con đã tự giải được bước nào, khen cụ thể quá trình con làm.",
            "Giữ một khung giờ học cố định mỗi tối, 25–30 phút rồi nghỉ ngắn.",
        ]
    highlights = []
    if days >= 3:
        highlights.append(f"Học đều đặn: có hoạt động {days} ngày.")
    if data["frequent_keywords"]:
        highlights.append("Chủ đề hay hỏi: " + ", ".join(data["frequent_keywords"][:4]) + ".")
    if data["wellbeing_alerts"]:
        target = "con" if audience == "parent" else "em"
        suggestions.insert(
            0,
            f"Hệ thống ghi nhận dấu hiệu {target} có lúc buồn hoặc áp lực. Hãy dành thời gian trò chuyện, lắng nghe {target}.",
        )
    return {"summary": summary, "highlights": highlights, "suggestions": suggestions, "generated_by": "template"}


async def narrative(
    model: ChatModel, name: str, data: dict[str, Any], audience: str = "parent"
) -> tuple[dict[str, Any], Usage | None]:
    system = NARRATIVE_SYSTEM.format(
        audience="phụ huynh" if audience == "parent" else "giáo viên",
        action="phụ huynh kèm con ở nhà" if audience == "parent" else "giáo viên hỗ trợ em trên lớp",
    )
    facts = {key: value for key, value in data.items() if key not in ("daily", "last_active")}
    try:
        answer, usage = await complete_json(model, f"Học sinh: {name}\nSố liệu: {facts}", system=system, max_tokens=600)
    except LLMError:
        return fallback_narrative(name, data, audience), None
    summary = str(answer.get("summary", "")).strip()
    if not summary:
        return fallback_narrative(name, data, audience), usage
    as_list = lambda key: [str(item)[:300] for item in answer.get(key, []) if item][:5]  # noqa: E731
    result = {"summary": summary[:800], "highlights": as_list("highlights"), "suggestions": as_list("suggestions")}
    if data["wellbeing_alerts"] and audience == "parent":
        # Always surfaced, whatever the model wrote.
        result["suggestions"].insert(0, fallback_narrative(name, data, audience)["suggestions"][0])
    return {**result, "generated_by": "llm"}, usage
