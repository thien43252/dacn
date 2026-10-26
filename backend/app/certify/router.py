"""Certification: start a run on a version, read reports, and the admin review queue."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.manifest import AgentManifest
from app.agents.models import Agent, AgentVersion
from app.agents.router import _own_agent
from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.certify.models import Certification
from app.certify.pipeline import apply_decision, run_certification

router = APIRouter(tags=["certification"])
Teacher = Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


class CertifyIn(BaseModel):
    # Make the agent public on the Hub as soon as this version is certified.
    publish: bool = False


class CertificationOut(BaseModel):
    id: str
    agent_id: str
    agent_slug: str
    agent_name: str
    author: str
    version_id: str
    version: int
    status: str
    score: float | None
    publish: bool
    progress: dict[str, Any]
    reasons: list[str]
    review_note: str
    created_at: datetime
    finished_at: datetime | None


class CertificationDetail(CertificationOut):
    report: dict[str, Any]


class ReviewIn(BaseModel):
    decision: Literal["certified", "rejected"]
    note: str = Field(default="", max_length=500)


class VisibilityIn(BaseModel):
    visibility: Literal["public", "private"]


async def _out(db, certification: Certification, detail: bool = False) -> CertificationOut | CertificationDetail:
    agent = await db.get(Agent, certification.agent_id)
    version = await db.get(AgentVersion, certification.agent_version_id)
    assert agent is not None and version is not None
    owner = await db.get(User, agent.owner_id) if agent.owner_id else None
    fields = {
        "id": certification.id,
        "agent_id": agent.id,
        "agent_slug": agent.slug,
        "agent_name": AgentManifest.model_validate(version.manifest).name,
        "author": "EduAgent Hub" if agent.is_platform else (owner.name if owner else "Người dùng đã xoá"),
        "version_id": version.id,
        "version": version.version,
        "status": certification.status,
        "score": certification.score,
        "publish": certification.publish,
        "progress": certification.progress or {},
        "reasons": (certification.report or {}).get("decision", {}).get("reasons", []),
        "review_note": certification.review_note,
        "created_at": certification.created_at,
        "finished_at": certification.finished_at,
    }
    if detail:
        return CertificationDetail(**fields, report=certification.report or {})
    return CertificationOut(**fields)


async def _readable(db, user: User, certification_id: str) -> Certification:
    certification = await db.get(Certification, certification_id)
    agent = await db.get(Agent, certification.agent_id) if certification else None
    if certification is None or agent is None or (agent.owner_id != user.id and user.role != Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy kết quả kiểm định.")
    return certification


@router.post(
    "/agents/{agent_id}/versions/{version_id}/certify",
    response_model=CertificationOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def certify(
    agent_id: str, version_id: str, payload: CertifyIn, user: Teacher, db: DbSession, background: BackgroundTasks
) -> CertificationOut:
    agent = await _own_agent(db, user, agent_id)
    version = await db.get(AgentVersion, version_id)
    if version is None or version.agent_id != agent.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên bản.")
    if version.certification_status == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Phiên bản này đang được kiểm định.")
    latest = await db.scalar(
        select(Certification)
        .where(Certification.agent_version_id == version.id)
        .order_by(Certification.created_at.desc())
        .limit(1)
    )
    if version.certification_status == "certified" and latest is not None:
        # Already certified: only the publish choice can change.
        if payload.publish:
            latest.publish = True
            agent.visibility = "public"
            await db.commit()
        return await _out(db, latest)
    certification = Certification(
        agent_id=agent.id, agent_version_id=version.id, requested_by=user.id, publish=payload.publish
    )
    version.certification_status = "pending"
    db.add(certification)
    await db.commit()
    background.add_task(run_certification, certification.id)
    return await _out(db, certification)


@router.get("/agents/{agent_id}/certifications", response_model=list[CertificationOut])
async def agent_certifications(agent_id: str, user: Teacher, db: DbSession) -> list[CertificationOut]:
    agent = await _own_agent(db, user, agent_id)
    rows = await db.scalars(
        select(Certification).where(Certification.agent_id == agent.id).order_by(Certification.created_at.desc())
    )
    return [await _out(db, row) for row in rows]


@router.get("/certifications/{certification_id}", response_model=CertificationDetail)
async def certification_detail(certification_id: str, user: CurrentUser, db: DbSession) -> CertificationDetail:
    certification = await _readable(db, user, certification_id)
    return await _out(db, certification, detail=True)  # type: ignore[return-value]


@router.patch("/agents/{agent_id}/visibility")
async def set_visibility(agent_id: str, payload: VisibilityIn, user: Teacher, db: DbSession) -> dict[str, str]:
    """Public agents appear on the Hub once they have a certified version; private ones stay with their author."""
    agent = await _own_agent(db, user, agent_id)
    agent.visibility = payload.visibility
    await db.commit()
    return {"visibility": agent.visibility}


@router.get("/admin/certifications", response_model=list[CertificationOut])
async def queue(
    _: Admin, db: DbSession, status_filter: str = Query(default="", alias="status")
) -> list[CertificationOut]:
    query = select(Certification).order_by(Certification.created_at.desc()).limit(200)
    if status_filter:
        query = query.where(Certification.status == status_filter)
    return [await _out(db, row) for row in await db.scalars(query)]


@router.post("/admin/certifications/{certification_id}/review", response_model=CertificationOut)
async def review(certification_id: str, payload: ReviewIn, user: Admin, db: DbSession) -> CertificationOut:
    certification = await _readable(db, user, certification_id)
    if certification.status in ("running", "failed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Chỉ duyệt được lần kiểm định đã chạy xong.")
    certification.reviewer_id = user.id
    certification.review_note = payload.note.strip()
    await apply_decision(db, certification, payload.decision)
    await db.commit()
    return await _out(db, certification)
