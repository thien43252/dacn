"""Safety audit log (guard events) for teachers and admins, and model usage and cost for admins."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.audit.models import GuardEvent
from app.auth.deps import DbSession, require_roles
from app.auth.models import Role, User
from app.chat.models import UsageRecord
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom

router = APIRouter(tags=["audit"])
Teacher = Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
SUMMARY_DAYS = 30


class GuardEventOut(BaseModel):
    id: str
    created_at: datetime
    source: str
    class_id: str | None
    class_name: str | None
    user_name: str | None
    role: str
    agent_slug: str | None
    stage: str
    verdict: str
    category: str
    detector: str
    severity: str
    reason: str
    excerpt: str


class AuditSummary(BaseModel):
    days: int
    total: int
    by_verdict: dict[str, int]
    by_category: dict[str, int]
    by_stage: dict[str, int]
    high_severity: int


class AuditOut(BaseModel):
    summary: AuditSummary
    events: list[GuardEventOut]


async def _events(db, query, limit: int) -> list[GuardEventOut]:
    rows = await db.execute(
        query.add_columns(ClassRoom.name, User.name)
        .outerjoin(ClassRoom, ClassRoom.id == GuardEvent.class_id)
        .outerjoin(User, User.id == GuardEvent.user_id)
        .order_by(GuardEvent.created_at.desc())
        .limit(limit)
    )
    return [
        GuardEventOut(
            id=event.id,
            created_at=event.created_at,
            source=event.source,
            class_id=event.class_id,
            class_name=class_name,
            user_name=user_name,
            role=event.role,
            agent_slug=event.agent_slug,
            stage=event.stage,
            verdict=event.verdict,
            category=event.category,
            detector=event.detector,
            severity=event.severity,
            reason=event.reason,
            excerpt=event.excerpt,
        )
        for event, class_name, user_name in rows
    ]


async def _summary(db, condition) -> AuditSummary:
    since = datetime.now(UTC) - timedelta(days=SUMMARY_DAYS)
    rows = (
        await db.execute(
            select(GuardEvent.verdict, GuardEvent.category, GuardEvent.stage, GuardEvent.severity).where(
                condition, GuardEvent.created_at >= since
            )
        )
    ).all()
    return AuditSummary(
        days=SUMMARY_DAYS,
        total=len(rows),
        by_verdict=dict(Counter(row.verdict for row in rows)),
        by_category=dict(Counter(row.category for row in rows if row.category)),
        by_stage=dict(Counter(row.stage for row in rows)),
        high_severity=sum(row.severity == "high" for row in rows),
    )


def _filters(query, stage: str, verdict: str):
    if stage:
        query = query.where(GuardEvent.stage == stage)
    if verdict:
        query = query.where(GuardEvent.verdict == verdict)
    return query


@router.get("/classes/{class_id}/audit", response_model=AuditOut)
async def class_audit(
    class_id: str,
    user: Teacher,
    db: DbSession,
    stage: str = Query(default=""),
    verdict: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    condition = (GuardEvent.class_id == room.id) & (GuardEvent.source == "chat")
    query = _filters(select(GuardEvent).where(condition), stage, verdict)
    return AuditOut(summary=await _summary(db, condition), events=await _events(db, query, limit))


@router.get("/audit/events", response_model=AuditOut)
async def audit_events(
    user: Teacher,
    db: DbSession,
    stage: str = Query(default=""),
    verdict: str = Query(default=""),
    source: str = Query(default="chat"),
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditOut:
    """Teachers: events from every class they teach. Admins: the whole platform, filtered by source."""
    if user.role == Role.ADMIN:
        condition = GuardEvent.source == source if source else GuardEvent.id.is_not(None)
    else:
        taught = select(ClassMember.class_id).where(ClassMember.user_id == user.id, ClassMember.role == "teacher")
        condition = GuardEvent.class_id.in_(taught) & (GuardEvent.source == "chat")
    query = _filters(select(GuardEvent).where(condition), stage, verdict)
    return AuditOut(summary=await _summary(db, condition), events=await _events(db, query, limit))


class UsageRow(BaseModel):
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    avg_latency_ms: int


class UsageOut(BaseModel):
    days: int
    total: UsageRow
    by_purpose: list[UsageRow]
    by_model: list[UsageRow]
    by_day: list[UsageRow]


async def _usage_rows(db, key, since: datetime) -> list[UsageRow]:
    rows = await db.execute(
        select(
            key.label("key"),
            func.count(),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
            func.coalesce(func.avg(UsageRecord.latency_ms), 0),
        )
        .where(UsageRecord.created_at >= since)
        .group_by(key)
        .order_by(key)
    )
    return [
        UsageRow(
            key=str(row[0]),
            calls=row[1],
            input_tokens=int(row[2]),
            output_tokens=int(row[3]),
            cost_usd=round(float(row[4]), 6),
            avg_latency_ms=int(row[5]),
        )
        for row in rows
    ]


@router.get("/admin/usage", response_model=UsageOut)
async def usage(_: Admin, db: DbSession, days: int = Query(default=7, ge=1, le=90)) -> UsageOut:
    since = datetime.now(UTC) - timedelta(days=days)
    by_purpose = await _usage_rows(db, UsageRecord.purpose, since)
    calls = sum(row.calls for row in by_purpose)
    total = UsageRow(
        key="total",
        calls=calls,
        input_tokens=sum(row.input_tokens for row in by_purpose),
        output_tokens=sum(row.output_tokens for row in by_purpose),
        cost_usd=round(sum(row.cost_usd for row in by_purpose), 6),
        avg_latency_ms=int(sum(row.avg_latency_ms * row.calls for row in by_purpose) / calls) if calls else 0,
    )
    return UsageOut(
        days=days,
        total=total,
        by_purpose=by_purpose,
        by_model=await _usage_rows(db, UsageRecord.model, since),
        by_day=await _usage_rows(db, func.date(UsageRecord.created_at), since),
    )
