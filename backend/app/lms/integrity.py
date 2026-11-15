"""Exam integrity for the agent runtime (research R8, FR-028).

While a student has an open attempt of a quiz with `block_agents`, no agent anywhere on the platform (class agents,
their own agents, agents in groups, handed-off agents) may give them the answers. The runtime asks this module:

- `active_exams(db, user_ids)`: the open exams of those users, with question texts and correct answers (server side
  only, never sent to a client);
- `matches_question(text, exams)`: does a message quote or paraphrase closely one of those questions (input check);
- `reveals_answer(reply, user_text, exams)`: does a reply give away a correct answer (output check, rules);
- `exam_context(exams)`: the question list handed to the LLM output reviewer to catch paraphrased answers.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import lms
from app.lms.models import Quiz, QuizAttempt, QuizQuestion
from app.textnorm import fold

# Weighted share of a question's words that must appear in a message for it to count as asking that question, and
# (lower) for a reply that gives a short answer to count as answering it.
EXAM_MATCH_THRESHOLD = 0.6
EXAM_VIEW_THRESHOLD = 0.45
# Questions shorter than this (after folding) are too generic to match on their own ("2 + 2 = ?").
MIN_QUESTION_CHARS = 12
# A correct answer this long is distinctive enough to block on sight, even without the question in view.
DISTINCTIVE_ANSWER_CHARS = 12

EXAM_BLOCKED = (
    "Bạn đang làm một bài kiểm tra trên lớp nên mình chưa thể giúp câu này. Làm xong bài, mình cùng xem lại nhé!"
)


@dataclass
class ExamQuestion:
    prompt: str
    answers: list[str] = field(default_factory=list)


@dataclass
class ActiveExam:
    attempt_id: str
    quiz_id: str
    student_id: str
    questions: list[ExamQuestion] = field(default_factory=list)


def _answers_of(question: QuizQuestion) -> list[str]:
    key = question.answer_key
    if question.kind in ("single", "multi"):
        wanted = set(key if isinstance(key, list) else [key])
        return [str(o.get("text", "")) for o in question.options or [] if o.get("id") in wanted and o.get("text")]
    if question.kind == "true_false" and isinstance(key, bool):
        return ["đúng" if key else "sai"]
    if question.kind == "short":
        return [str(a) for a in (key if isinstance(key, list) else [key]) if a]
    rubric = question.rubric or {}
    return [str(rubric["model_answer"])] if rubric.get("model_answer") else []


async def active_exams(db: AsyncSession, user_ids: list[str]) -> list[ActiveExam]:
    if not user_ids:
        return []
    current = lms.now()
    rows = await db.execute(
        select(QuizAttempt)
        .join(Quiz, Quiz.item_id == QuizAttempt.quiz_id)
        .where(
            QuizAttempt.student_id.in_(user_ids),
            QuizAttempt.status == "in_progress",
            Quiz.block_agents.is_(True),
            or_(QuizAttempt.deadline_at.is_(None), QuizAttempt.deadline_at > current),
        )
    )
    attempts = list(rows.scalars())
    if not attempts:
        return []
    quiz_ids = {a.quiz_id for a in attempts}
    questions: dict[str, list[ExamQuestion]] = {quiz_id: [] for quiz_id in quiz_ids}
    for question in await db.scalars(
        select(QuizQuestion).where(QuizQuestion.quiz_id.in_(quiz_ids)).order_by(QuizQuestion.position)
    ):
        questions[question.quiz_id].append(ExamQuestion(question.prompt, _answers_of(question)))
    # SQLite returns naive datetimes; the SQL filter above is a coarse pass, this is the exact one.
    return [
        ActiveExam(a.id, a.quiz_id, a.student_id, questions[a.quiz_id])
        for a in attempts
        if a.deadline_at is None or lms.aware(a.deadline_at) > current
    ]


# Words too common in question stems to identify one ("giá trị của x là bao nhiêu").
STOPWORDS = {
    "la",
    "cua",
    "bao",
    "nhieu",
    "gi",
    "the",
    "nao",
    "cau",
    "bai",
    "cho",
    "biet",
    "hay",
    "tim",
    "tinh",
    "va",
    "co",
    "khong",
    "nhung",
    "mot",
    "cac",
    "nay",
    "do",
    "voi",
    "trong",
    "duoc",
    "de",
    "thi",
    "ma",
    "o",
    "a",
    "an",
    "of",
    "is",
    "what",
    "which",
    "how",
    "many",
    "in",
    "to",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(text)))


def _weight(token: str) -> float:
    if any(char.isdigit() for char in token):
        return 3.0  # numbers and expressions identify a question best
    return 0.3 if token in STOPWORDS else 1.0


def _coverage(text_tokens: set[str], question: ExamQuestion) -> float:
    """Weighted share of the question's words present in a text (0 for questions too short to identify)."""
    if len(fold(question.prompt)) < MIN_QUESTION_CHARS:
        return 0.0
    tokens = _tokens(question.prompt)
    total = sum(_weight(t) for t in tokens)
    return sum(_weight(t) for t in tokens & text_tokens) / total if total else 0.0


def matches_question(text: str, exams: list[ActiveExam]) -> ExamQuestion | None:
    """The open exam question that `text` quotes or closely paraphrases, if any."""
    tokens = _tokens(text)
    if not tokens:
        return None
    for exam in exams:
        for question in exam.questions:
            if _coverage(tokens, question) >= EXAM_MATCH_THRESHOLD:
                return question
    return None


def _contains_answer(reply_folded: str, answer: str) -> bool:
    target = re.sub(r"\s+", " ", fold(answer)).strip()
    if not target:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])", reply_folded) is not None


def reveals_answer(reply: str, user_text: str, exams: list[ActiveExam]) -> bool:
    """Rule check on a reply: a correct answer of a question that is in view (quoted in the message or the reply), or
    a distinctive correct answer anywhere."""
    if not reply.strip():
        return False
    reply_folded = re.sub(r"\s+", " ", fold(reply))
    in_view = _tokens(user_text) | _tokens(reply)
    for exam in exams:
        for question in exam.questions:
            quoted = _coverage(in_view, question) >= EXAM_VIEW_THRESHOLD
            for answer in question.answers:
                long_enough = len(fold(answer)) >= DISTINCTIVE_ANSWER_CHARS
                if (quoted or long_enough) and _contains_answer(reply_folded, answer):
                    return True
    return False


def exam_context(exams: list[ActiveExam], limit: int = 30) -> str:
    """Numbered questions with their answers, for the LLM reviewer only."""
    lines: list[str] = []
    for exam in exams:
        for question in exam.questions:
            if len(lines) >= limit:
                break
            answers = "; ".join(question.answers)
            lines.append(
                f"{len(lines) + 1}. {question.prompt[:300]}" + (f" (đáp án: {answers[:200]})" if answers else "")
            )
    return "\n".join(lines)
