import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

import app.models  # noqa: F401
from app.agents.service import sync_platform_agents
from app.db import Base, use_sessionmaker
from app.llm.fake import FakeChatModel, FakeEmbedder
from app.llm.registry import use_chat_model, use_embedder
from app.main import create_app


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A fresh database per test: in-memory SQLite by default, or Postgres when TEST_DATABASE_URL is set.

    Postgres runs catch dialect differences (JSON, booleans, pgvector) that SQLite hides:
    TEST_DATABASE_URL=postgresql+asyncpg://eduagent:eduagent@127.0.0.1:5433/eduagent_test uv run pytest
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    else:
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def app(sessionmaker, fake_llm, fake_embedder):
    use_sessionmaker(sessionmaker)
    async with sessionmaker() as db:
        await sync_platform_agents(db)
    application = create_app()
    yield application
    use_sessionmaker(None)


@pytest.fixture
def fake_llm():
    model = FakeChatModel()
    use_chat_model(model)
    yield model
    use_chat_model(None)


@pytest.fixture
def fake_embedder():
    embedder = FakeEmbedder()
    use_embedder(embedder)
    yield embedder
    use_embedder(None)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def as_user(app):
    """`await as_user("teacher")` returns a logged-in client of its own, so several users can act in one test."""
    clients: list[AsyncClient] = []
    counter = 0

    async def make(role: str, name: str | None = None) -> AsyncClient:
        nonlocal counter
        counter += 1
        http = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(http)
        payload = {
            "name": name or f"{role.title()} {counter}",
            "email": f"{role}{counter}@example.com",
            "password": "Secret123",
            "role": role,
        }
        response = await http.post("/api/auth/register", json=payload)
        assert response.status_code == 201, response.text
        http.user = response.json()["user"]  # type: ignore[attr-defined]
        return http

    yield make
    for http in clients:
        await http.aclose()
