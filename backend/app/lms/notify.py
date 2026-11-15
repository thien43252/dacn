"""In-app notifications (research R10). `dedupe_key` makes every producer safe to run more than once."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import lms
from app.auth.deps import CurrentUser, DbSession
from app.lms.models import Notification
from app.lms.schemas import NotificationOut

router = APIRouter(tags=["lms"])


async def notify(
    db: AsyncSession,
    user_ids: list[str],
    kind: str,
    title: str,
    link: str = "",
    class_id: str | None = None,
    dedupe_key: str = "",
) -> int:
    """Adds one notification per user unless `<dedupe_key>:<user_id>` already exists. Returns how many were added.
    The caller commits."""
    if not user_ids:
        return 0
    keys = {user_id: f"{dedupe_key or kind}:{user_id}"[:120] for user_id in dict.fromkeys(user_ids)}
    existing = set(await db.scalars(select(Notification.dedupe_key).where(Notification.dedupe_key.in_(keys.values()))))
    pending = {row.dedupe_key for row in db.new if isinstance(row, Notification)}
    added = 0
    for user_id, key in keys.items():
        if key in existing or key in pending:
            continue
        db.add(
            Notification(
                user_id=user_id, kind=kind, class_id=class_id, title=title[:200], link=link[:300], dedupe_key=key
            )
        )
        added += 1
    return added


def _out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        kind=row.kind,
        class_id=row.class_id,
        title=row.title,
        link=row.link,
        read_at=row.read_at,
        created_at=row.created_at,
    )


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class ReadIn(BaseModel):
    ids: list[str] | None = None


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(user: CurrentUser, db: DbSession, unread: int = 0, limit: int = 50) -> NotificationList:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread:
        query = query.where(Notification.read_at.is_(None))
    rows = await db.scalars(query.order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 200)))
    count = await db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return NotificationList(items=[_out(row) for row in rows], unread_count=count or 0)


@router.post("/notifications/read", response_model=NotificationList)
async def mark_read(body: ReadIn, user: CurrentUser, db: DbSession) -> NotificationList:
    stamp: datetime = lms.now()
    query = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if body.ids:
        query = query.where(Notification.id.in_(body.ids))
    await db.execute(query.values(read_at=stamp))
    await db.commit()
    return await list_notifications(user, db, unread=0)
