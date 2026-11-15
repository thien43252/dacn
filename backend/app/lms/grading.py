"""Pure grading functions (research R7, R12). No I/O, no database: callers pass plain values."""

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

_SPACES = re.compile(r"\s+")


def normalize_short(text: object) -> str:
    """Short answers compare after NFC, casefold and whitespace collapsing. Vietnamese diacritics are kept on purpose:
    removing them changes meaning ("ma" vs "má")."""
    if text is None:
        return ""
    value = unicodedata.normalize("NFC", str(text)).casefold()
    return _SPACES.sub(" ", value).strip()


def _round(value: float) -> float:
    return round(value + 0.0, 2)


def grade_question(
    kind: str, answer_key: object, value: object, points: float, multi_scoring: str = "all_or_nothing"
) -> float | None:
    """Points earned on one question, or None when a teacher must grade it (essay)."""
    if kind == "essay":
        return None
    if value is None or value == "" or value == []:
        return 0.0
    if kind == "single":
        return _round(points) if value == answer_key else 0.0
    if kind == "true_false":
        return _round(points) if isinstance(value, bool) and value == answer_key else 0.0
    if kind == "short":
        accepted = answer_key if isinstance(answer_key, list) else [answer_key]
        given = normalize_short(value)
        return _round(points) if given and any(given == normalize_short(a) for a in accepted) else 0.0
    if kind == "multi":
        correct = set(answer_key or [])
        chosen = set(value) if isinstance(value, list) else {value}
        if not correct:
            return 0.0
        if multi_scoring == "partial":
            right = len(chosen & correct)
            wrong = len(chosen - correct)
            return _round(max(0.0, (right - wrong) / len(correct)) * points)
        return _round(points) if chosen == correct else 0.0
    return 0.0


def attempt_total(item_scores: dict, question_ids: Iterable[str]) -> float | None:
    """Sum of the per-question points, or None while any question is still ungraded."""
    total = 0.0
    for question_id in question_ids:
        entry = item_scores.get(question_id)
        if not entry or entry.get("points") is None:
            return None
        total += float(entry["points"])
    return _round(total)


@dataclass
class GradedAttempt:
    attempt_no: int
    score: float | None
    max_score: float


def quiz_score(attempts: list[GradedAttempt], policy: str = "best") -> float | None:
    """The quiz result on the quiz's own scale over attempts that are fully graded (`score` not None)."""
    graded = [a for a in attempts if a.score is not None]
    if not graded:
        return None
    if policy == "last":
        return _round(max(graded, key=lambda a: a.attempt_no).score or 0.0)
    if policy == "average":
        return _round(sum(a.score or 0.0 for a in graded) / len(graded))
    return _round(max(a.score or 0.0 for a in graded))


def to_ten(score: float | None, max_score: float) -> float | None:
    """Gradebook averages use a 0–10 scale (research R11)."""
    if score is None or max_score <= 0:
        return None
    return _round(score / max_score * 10)


@dataclass
class LatePenalty:
    days_late: int
    penalty: float
    final: float | None


def days_late(submitted_at: datetime, effective_due: datetime | None) -> int:
    """Whole days late, rounded up: 2 days 3 hours late counts as 3 days."""
    if effective_due is None or submitted_at <= effective_due:
        return 0
    return math.ceil((submitted_at - effective_due).total_seconds() / 86400)


def late_penalty(
    raw: float | None,
    max_points: float,
    submitted_at: datetime,
    effective_due: datetime | None,
    per_day_pct: float,
    max_pct: float,
    waived: bool = False,
) -> LatePenalty:
    """Research R12: penalty = min(per_day% × days, max%) of max_points; final = max(0, raw − penalty), or raw when
    the teacher waived it."""
    days = days_late(submitted_at, effective_due)
    # A cap of 0 means "no cap" (the teacher only set a per-day rate); never more than the whole score.
    cap = max_pct if max_pct > 0 else 100.0
    pct = min(max(per_day_pct, 0.0) * days, cap, 100.0)
    penalty = 0.0 if waived else _round(pct / 100 * max_points)
    final = None if raw is None else _round(max(0.0, raw - penalty))
    return LatePenalty(days_late=days, penalty=penalty, final=final)
