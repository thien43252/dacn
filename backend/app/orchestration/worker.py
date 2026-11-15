"""The in-process worker (research R1): runs queued handoffs, resumes runs and expires questions and cards.

One asyncio task inside the backend process; work lives in Postgres (handoffs, agent_runs), so a reload loses
nothing: running handoffs carry a lease and are claimed again once it expires. Tests disable the loop and call
`drain()`, which does the same work one job at a time.
"""

import asyncio
import contextlib
import logging

from app.config import get_settings
from app.db import session_factory
from app.orchestration import handoffs, runs

log = logging.getLogger("eduagent.worker")
_task: asyncio.Task | None = None


async def tick(*, concurrent: bool = True) -> int:
    from app.runtime.run import expire_cards, resume

    async with session_factory()() as db:
        await expire_cards(db)
        await db.commit()
        handoff_ids = await handoffs.claimable_ids(db)
        run_ids = await runs.resumable_ids(db)
    jobs = [handoffs.execute(handoff_id) for handoff_id in handoff_ids] + [resume(run_id) for run_id in run_ids]
    if not jobs:
        return 0
    if concurrent:
        results = await asyncio.gather(*jobs, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.error("worker job failed: %r", result)
    else:
        for job in jobs:
            await job
    return len(jobs)


async def drain(max_rounds: int = 50) -> int:
    """Runs every queued job until nothing is left (tests, scripts)."""
    total = 0
    for _ in range(max_rounds):
        done = await tick(concurrent=False)
        total += done
        if not done:
            break
    return total


async def recover() -> None:
    """At startup: runs that were mid-flight when the process died are failed; leases handle handoffs."""
    from sqlalchemy import update

    from app.orchestration.models import AgentRun

    async with session_factory()() as db:
        await db.execute(
            update(AgentRun)
            .where(AgentRun.status == "running", AgentRun.handoff_id.is_(None), AgentRun.source == "chat")
            .values(status="failed")
        )
        await db.commit()


async def _loop() -> None:
    interval = get_settings().worker_poll_seconds
    while True:
        try:
            await tick()
        except Exception:
            log.exception("worker tick failed")
        await asyncio.sleep(interval)


async def start() -> None:
    global _task
    if _task is None:
        try:
            await recover()
        except Exception:
            log.exception("worker recovery failed")
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
