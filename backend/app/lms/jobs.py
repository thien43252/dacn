"""Periodic LMS work run from `orchestration.worker.tick` (and directly by tests).

Each step must be idempotent: the worker may run them every second and after restarts.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

# Steps register themselves here (lessons: scheduled publish; quizzes: close overdue attempts; gradebook: due-soon
# reminders). Each takes a session and commits its own work.
STEPS: list[Callable[[AsyncSession], Awaitable[None]]] = []


def step(fn: Callable[[AsyncSession], Awaitable[None]]) -> Callable[[AsyncSession], Awaitable[None]]:
    STEPS.append(fn)
    return fn


async def run_due(db: AsyncSession) -> None:
    import app.lms.assignments  # noqa: F401  (modules register their steps on import)
    import app.lms.gradebook  # noqa: F401
    import app.lms.lessons  # noqa: F401
    import app.lms.quizzes  # noqa: F401

    for fn in STEPS:
        await fn(db)
