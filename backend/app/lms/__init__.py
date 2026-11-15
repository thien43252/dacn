"""Feature 004 (LMS): lessons, quizzes, assignments, gradebook. See specs/004-lms-lessons."""

from datetime import UTC, datetime


def now() -> datetime:
    """The single clock of the LMS (tests patch `app.lms.now`). Always timezone-aware UTC."""
    return datetime.now(UTC)


def aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC so comparisons with `now()` work on both databases."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
