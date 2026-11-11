from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app


async def test_health_does_not_need_database() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine": get_settings().runtime_engine,
        "orchestrator": "on" if get_settings().dify_planner_key else "off",
    }


async def test_health_reports_orchestrator_by_planner_key(monkeypatch) -> None:
    """Feature 002: multi-step handling is off without DIFY_PLANNER_KEY (contracts/chat-sse.md, Health)."""
    states = []
    for key in ("", "app-planner"):
        monkeypatch.setenv("DIFY_PLANNER_KEY", key)
        get_settings.cache_clear()
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            states.append((await client.get("/api/health")).json()["orchestrator"])
    monkeypatch.undo()
    get_settings.cache_clear()
    assert states == ["off", "on"]


async def test_health_reports_dify_engine(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_ENGINE", "dify")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            response = await client.get("/api/health")
    finally:
        monkeypatch.undo()  # restore the environment before dropping the cached dify settings
        get_settings.cache_clear()
    assert response.json()["engine"] == "dify"


async def test_ready_reports_database_down_without_failing(monkeypatch) -> None:
    async def unreachable() -> bool:
        return False

    monkeypatch.setattr("app.main.ping_database", unreachable)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "down"}
