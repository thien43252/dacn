import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthSession, Role, User
from app.auth.passwords import hash_password, verify_password


class EmailTakenError(Exception):
    pass


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo; Postgres keeps it. Both store UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def create_user(db: AsyncSession, *, name: str, email: str, password: str, role: Role) -> User:
    if await get_user_by_email(db, email):
        raise EmailTakenError(email)
    user = User(name=name, email=email, role=role.value, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


async def start_session(db: AsyncSession, user: User, hours: int) -> str:
    """Returns the raw token for the cookie; only its hash is persisted."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=hours)
    db.add(AuthSession(token_hash=_hash_token(token), user_id=user.id, expires_at=expires_at))
    await db.commit()
    return token


async def resolve_session(db: AsyncSession, token: str) -> User | None:
    session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
    if session is None:
        return None
    if _as_utc(session.expires_at) <= datetime.now(UTC):
        await db.delete(session)
        await db.commit()
        return None
    user = await db.get(User, session.user_id)
    return user if user and user.is_active else None


async def end_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
    await db.commit()
