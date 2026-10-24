from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_does_not_need_database() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_database_down_without_failing(monkeypatch) -> None:
    async def unreachable() -> bool:
        return False

    monkeypatch.setattr("app.main.ping_database", unreachable)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "down"}
