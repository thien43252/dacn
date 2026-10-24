from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, update

from app.auth.deps import require_roles
from app.auth.models import AuthSession, Role, User
from app.auth.passwords import hash_password, verify_password
from app.config import get_settings

COOKIE = get_settings().session_cookie_name
TEACHER = {"name": "Cô Hà", "email": "Ha@Example.com", "password": "Secret123", "role": "teacher"}


async def test_register_sets_cookie_and_normalizes_email(client) -> None:
    response = await client.post("/api/auth/register", json=TEACHER)
    assert response.status_code == 201
    assert response.json()["user"] == {
        "id": response.json()["user"]["id"],
        "name": "Cô Hà",
        "email": "ha@example.com",
        "role": "teacher",
    }
    assert COOKIE in response.cookies

    session = await client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == "ha@example.com"


async def test_register_rejects_duplicate_email(client) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    response = await client.post("/api/auth/register", json={**TEACHER, "email": "ha@example.com"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Email này đã được đăng ký."


async def test_register_cannot_self_assign_admin(client) -> None:
    response = await client.post("/api/auth/register", json={**TEACHER, "role": "admin"})
    assert response.status_code == 422


async def test_register_returns_vietnamese_validation_message(client) -> None:
    response = await client.post("/api/auth/register", json={**TEACHER, "password": "short"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Dùng ít nhất 8 ký tự, gồm chữ hoa, chữ thường và số."


async def test_login_uses_one_message_for_wrong_email_and_password(client) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    client.cookies.clear()
    wrong_password = await client.post("/api/auth/login", json={"email": "ha@example.com", "password": "Nope12345"})
    unknown = await client.post("/api/auth/login", json={"email": "who@example.com", "password": "Nope12345"})
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json()["detail"] == unknown.json()["detail"]

    ok = await client.post("/api/auth/login", json={"email": "HA@example.com ", "password": "Secret123"})
    assert ok.status_code == 200
    assert COOKIE in ok.cookies


async def test_logout_revokes_session(client) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    token = client.cookies[COOKIE]
    assert (await client.post("/api/auth/logout")).json() == {"ok": True}
    # Replaying the old token after logout must not work.
    client.cookies.set(COOKIE, token)
    assert (await client.get("/api/auth/session")).status_code == 401


async def test_session_requires_cookie(client) -> None:
    response = await client.get("/api/auth/session")
    assert response.status_code == 401
    assert response.json()["detail"] == "Bạn cần đăng nhập."


async def test_expired_session_is_rejected_and_removed(client, sessionmaker) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    async with sessionmaker() as db:
        await db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await db.commit()
    assert (await client.get("/api/auth/session")).status_code == 401
    async with sessionmaker() as db:
        assert (await db.scalars(select(AuthSession))).all() == []


async def test_only_hash_of_token_is_stored(client, sessionmaker) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    token = client.cookies[COOKIE]
    async with sessionmaker() as db:
        stored = (await db.scalars(select(AuthSession.token_hash))).one()
    assert stored != token and len(stored) == 64


async def test_require_roles_allows_and_forbids(app, client, sessionmaker) -> None:
    probe = APIRouter()

    @probe.get("/api/probe/teacher-only")
    async def teacher_only(user: Annotated[User, Depends(require_roles(Role.TEACHER))]) -> dict[str, str]:
        return {"role": user.role}

    app.include_router(probe)

    assert (await client.get("/api/probe/teacher-only")).status_code == 401

    await client.post("/api/auth/register", json={**TEACHER, "email": "student@example.com", "role": "student"})
    forbidden = await client.get("/api/probe/teacher-only")
    assert forbidden.status_code == 403

    await client.post("/api/auth/logout")
    await client.post("/api/auth/register", json=TEACHER)
    assert (await client.get("/api/probe/teacher-only")).json() == {"role": "teacher"}


async def test_inactive_user_cannot_log_in(client, sessionmaker) -> None:
    await client.post("/api/auth/register", json=TEACHER)
    async with sessionmaker() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    assert (await client.get("/api/auth/session")).status_code == 401
    login = await client.post("/api/auth/login", json={"email": "ha@example.com", "password": "Secret123"})
    assert login.status_code == 401


def test_password_hash_roundtrip() -> None:
    stored = hash_password("Secret123")
    assert stored.startswith("scrypt$")
    assert verify_password("Secret123", stored)
    assert not verify_password("secret123", stored)
    assert not verify_password("Secret123", "garbage")
