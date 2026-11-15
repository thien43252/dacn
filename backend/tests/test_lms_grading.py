import unicodedata
from datetime import UTC, datetime, timedelta

import pytest

from app.lms.grading import GradedAttempt, attempt_total, days_late, grade_question, late_penalty, quiz_score


@pytest.mark.parametrize(
    "kind,key,value,mode,expected",
    [
        ("single", "a", "a", "all_or_nothing", 3),
        ("single", "a", "b", "all_or_nothing", 0),
        ("true_false", False, False, "all_or_nothing", 3),
        ("true_false", True, False, "all_or_nothing", 0),
        ("true_false", True, 1, "all_or_nothing", 0),
        ("short", ["Hà Nội", "Thăng Long"], "  HÀ   NỘI ", "all_or_nothing", 3),
        ("short", ["Hà Nội", "Thăng Long"], "thăng long", "all_or_nothing", 3),
        ("short", ["má"], unicodedata.normalize("NFD", "MÁ"), "all_or_nothing", 3),
        ("short", ["má"], "ma", "all_or_nothing", 0),
        ("multi", ["a", "b"], ["b", "a", "a"], "all_or_nothing", 3),
        ("multi", ["a", "b"], ["a"], "all_or_nothing", 0),
        ("multi", ["a", "b"], ["a", "b", "c"], "all_or_nothing", 0),
        ("multi", ["a", "b"], ["a"], "partial", 1.5),
        ("multi", ["a", "b"], ["a", "b", "c"], "partial", 1.5),
        ("multi", ["a", "b"], ["a", "c", "d"], "partial", 0),
        ("multi", ["a", "b", "c", "d", "e", "f", "g"], ["a"], "partial", 0.43),
        ("essay", None, "Bài làm", "all_or_nothing", None),
    ],
)
def test_grade_question_values(kind, key, value, mode, expected):
    assert grade_question(kind, key, value, 3, mode) == expected


@pytest.mark.parametrize("kind,key", [("single", "a"), ("multi", ["a"]), ("true_false", True), ("short", ["a"])])
@pytest.mark.parametrize("value", [None, "", []])
def test_unanswered_objective_questions(kind, key, value):
    assert grade_question(kind, key, value, 3) == 0


def test_attempt_totals_and_quiz_policies():
    assert attempt_total({"a": {"points": 1.11}, "b": {"points": 2.22}}, ["a", "b"]) == 3.33
    assert attempt_total({"a": {"points": 1}}, ["a", "b"]) is None
    attempts = [GradedAttempt(1, 8, 10), GradedAttempt(2, 4, 10), GradedAttempt(3, None, 10)]
    assert quiz_score(attempts, "best") == 8
    assert quiz_score(attempts, "last") == 4
    assert quiz_score(attempts, "average") == 6
    assert quiz_score([attempts[-1]], "best") is None


def test_late_penalty_rounding_caps_and_waiver():
    due = datetime(2026, 1, 1, tzinfo=UTC)
    submitted = due + timedelta(days=2, hours=3)
    assert days_late(submitted, due) == 3
    assert days_late(due, due) == 0
    assert days_late(submitted, None) == 0
    result = late_penalty(8, 10, submitted, due, 10, 30)
    assert (result.days_late, result.penalty, result.final) == (3, 3.0, 5.0)
    assert late_penalty(8, 10, submitted, due, 20, 0).penalty == 6
    assert late_penalty(2, 10, submitted, due, 50, 0).final == 0
    assert late_penalty(8, 10, submitted, due, 10, 30, waived=True).final == 8
    assert late_penalty(8, 10, submitted, due, 0, 0).final == 8
