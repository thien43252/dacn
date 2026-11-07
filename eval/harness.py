"""Shared setup for the experiment scripts: an in-memory database with the platform agents and an eval user, so
experiments never write into the demo database. The model provider comes from backend/.env (LLM_PROVIDER...).

Agents run on Dify: the scripts need DIFY_BASE_URL and the app keys in .env. `--engine dify` (the only value now)
is kept so result rows and file names stay comparable with the engine comparison in docs/BAO-CAO.md (FR-024).
"""

import csv
import os
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.agents.service import sync_platform_agents  # noqa: E402
from app.auth.models import Role, User  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, use_sessionmaker  # noqa: E402

RESULTS = ROOT / "results"
ENGINES = ["dify"]


def use_engine(engine: str) -> str:
    os.environ["RUNTIME_ENGINE"] = engine
    get_settings.cache_clear()
    return engine


def suffixed(name: str, engine: str) -> str:
    """`<stem>_dify<ext>`: the files without the suffix hold the earlier in-process engine's results."""
    stem, dot, ext = name.rpartition(".")
    return f"{stem}_{engine}{dot}{ext}"


def percentile(values: list[int], q: float) -> int:
    values = sorted(v for v in values if v is not None)
    return values[min(len(values) - 1, int(len(values) * q))] if values else 0


async def setup() -> tuple[async_sessionmaker[AsyncSession], User]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    use_sessionmaker(factory)
    async with factory() as db:
        await sync_platform_agents(db)
        user = User(name="Eval", email="eval@example.com", password_hash="-", role=Role.TEACHER)
        db.add(user)
        await db.commit()
    return factory, user


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rate(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})" if denominator else "–"
