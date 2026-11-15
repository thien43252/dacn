"""Agent Hub, installations (class and personal) and the agent builder."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select

from app.agents.manifest import FALLBACK_SLUG, AgentManifest
from app.agents.models import Agent, AgentVersion, Installation
from app.agents.service import ResolvedAgent, latest_version
from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.certify.models import Certification
from app.classes import service as classes
from app.tools.registry import TOOLS

router = APIRouter(tags=["agents"])
Teacher = Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))]
# Feature 003: students and parents build agents too (FR-001). What they may pick is filtered by role below.
Maker = Annotated[User, Depends(require_roles(Role.TEACHER, Role.STUDENT, Role.PARENT, Role.ADMIN))]


class HubAgentOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    avatar: str
    subjects: list[str]
    grades: list[int]
    target_roles: list[str]
    tools: list[str]
    knowledge: str
    capabilities: list[str]
    is_platform: bool
    author: str
    version: int
    version_id: str
    certification_status: str
    install_count: int
    updated_at: datetime


class AgentDetailOut(HubAgentOut):
    manifest: dict[str, Any]
    visibility: str
    is_mine: bool
    forked_from_id: str | None
    draft_manifest: dict[str, Any] | None = None
    versions: list[dict[str, Any]] = []
    # Latest finished certification of the shown version: status, score, cases per category (public summary).
    certification: dict[str, Any] | None = None


class InstallIn(BaseModel):
    agent_id: str
    # Defaults to the newest version the caller may install.
    version_id: str | None = None


class InstallationOut(BaseModel):
    id: str
    scope: str
    enabled: bool
    agent: HubAgentOut
    created_at: datetime
    # Feature 003: the version's handoff grants and the class's narrowing of them (null: as granted).
    handoff_to: list[str] = []
    handoff_allow: list[str] | None = None


class ManifestIn(BaseModel):
    manifest: dict[str, Any]


class ToggleIn(BaseModel):
    enabled: bool | None = None
    # A teacher narrowing the agent's handoff grants in this class (FR-006): a subset of the manifest's list, or
    # null to keep it as granted. Send `reset_handoffs` to go back to null.
    handoff_allow: list[str] | None = None
    reset_handoffs: bool = False


async def _author(db, agent: Agent) -> str:
    if agent.is_platform:
        return "EduAgent Hub"
    owner = await db.get(User, agent.owner_id) if agent.owner_id else None
    return owner.name if owner else "Người dùng đã xoá"


async def _out(db, agent: Agent, version: AgentVersion | None) -> HubAgentOut:
    """Summary of `version`, or of the draft when the agent has no version yet (only its author sees that)."""
    manifest = AgentManifest.model_validate(version.manifest if version else agent.draft_manifest)
    return HubAgentOut(
        id=agent.id,
        slug=agent.slug,
        name=manifest.name,
        description=manifest.description,
        avatar=manifest.avatar,
        subjects=manifest.subjects,
        grades=manifest.grades,
        target_roles=list(manifest.target_roles),
        tools=manifest.tools,
        knowledge=manifest.knowledge,
        capabilities=manifest.capabilities,
        is_platform=agent.is_platform,
        author=await _author(db, agent),
        version=version.version if version else 0,
        version_id=version.id if version else "",
        certification_status=version.certification_status if version else "uncertified",
        install_count=await db.scalar(select(func.count()).where(Installation.agent_id == agent.id)) or 0,
        updated_at=agent.updated_at,
    )


async def certified_version(db, agent_id: str) -> AgentVersion | None:
    return await db.scalar(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id, AgentVersion.certification_status == "certified")
        .order_by(AgentVersion.version.desc())
        .limit(1)
    )


def validate_manifest(data: dict[str, Any]) -> AgentManifest:
    try:
        manifest = AgentManifest.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        message = str(first["msg"]).removeprefix("Value error, ")
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Manifest không hợp lệ ({field}): {message}"
        ) from None
    unknown = [tool for tool in manifest.tools if tool not in TOOLS or TOOLS[tool].meta]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Công cụ không có trong danh mục: {', '.join(unknown)}"
        )
    return manifest


# ---------------- Hub ----------------


@router.get("/hub/agents", response_model=list[HubAgentOut])
async def hub(
    user: CurrentUser,
    db: DbSession,
    q: str = Query(default="", max_length=100),
    subject: str = Query(default=""),
    grade: int | None = Query(default=None, ge=1, le=12),
    role: str = Query(default=""),
) -> list[HubAgentOut]:
    """Public agents with a certified version. Students and parents only see agents made for their role."""
    agents = await db.scalars(
        select(Agent).where(Agent.visibility == "public").order_by(Agent.is_platform.desc(), Agent.slug)
    )
    wanted_role = user.role if user.role in ("student", "parent") else role
    needle = q.strip().lower()
    out = []
    for agent in agents:
        version = await certified_version(db, agent.id)
        if version is None:
            continue
        manifest = AgentManifest.model_validate(version.manifest)
        if wanted_role and wanted_role not in manifest.target_roles:
            continue
        if subject and subject not in manifest.subjects and "chung" not in manifest.subjects:
            continue
        if grade and manifest.grades and grade not in manifest.grades:
            continue
        haystack = " ".join([manifest.name, manifest.description, *manifest.capabilities]).lower()
        if needle and needle not in haystack:
            continue
        out.append(await _out(db, agent, version))
    return out


async def _viewable(db, user: User, agent_id: str) -> tuple[Agent, AgentVersion | None, bool]:
    """An agent the user may look at: their own (newest version or draft), or public with a certified version."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    mine = agent.owner_id == user.id or user.role == Role.ADMIN
    if mine:
        return agent, await latest_version(db, agent.id), True
    version = await certified_version(db, agent.id)
    if agent.visibility != "public" or version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    return agent, version, False


@router.get("/hub/agents/{agent_id}", response_model=AgentDetailOut)
async def hub_detail(agent_id: str, user: CurrentUser, db: DbSession) -> AgentDetailOut:
    agent, version, mine = await _viewable(db, user, agent_id)
    versions = []
    if mine:
        rows = await db.scalars(
            select(AgentVersion).where(AgentVersion.agent_id == agent.id).order_by(AgentVersion.version.desc())
        )
        versions = [
            {
                "id": v.id,
                "version": v.version,
                "certification_status": v.certification_status,
                "created_at": v.created_at,
            }
            for v in rows
        ]
    summary = None
    if version is not None:
        latest = await db.scalar(
            select(Certification)
            .where(Certification.agent_version_id == version.id, Certification.finished_at.is_not(None))
            .order_by(Certification.created_at.desc())
            .limit(1)
        )
        if latest is not None:
            report = latest.report or {}
            summary = {
                "id": latest.id,
                "status": latest.status,
                "score": latest.score,
                "cases": len(report.get("cases", [])),
                "by_category": report.get("by_category", {}),
                "finished_at": latest.finished_at,
            }
    return AgentDetailOut(
        **(await _out(db, agent, version)).model_dump(),
        certification=summary,
        manifest=version.manifest if version else agent.draft_manifest,
        visibility=agent.visibility,
        is_mine=mine,
        forked_from_id=agent.forked_from_id,
        draft_manifest=agent.draft_manifest if mine else None,
        versions=versions,
    )


# ---------------- Installations ----------------


async def _installable(db, user: User, payload: InstallIn) -> tuple[Agent, AgentVersion]:
    agent = await db.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    own = agent.owner_id == user.id
    if payload.version_id:
        version = await db.get(AgentVersion, payload.version_id)
        if version is None or version.agent_id != agent.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phiên bản.")
        if not own and version.certification_status != "certified":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ cài được phiên bản đã kiểm định của agent người khác.")
    else:
        version = await latest_version(db, agent.id) if own else await certified_version(db, agent.id)
    if version is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Agent chưa có phiên bản để cài. Hãy “Tạo phiên bản” trong trình tạo agent."
        )
    if not own and agent.visibility != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    return agent, version


async def _installation_out(db, installation: Installation) -> InstallationOut:
    agent = await db.get(Agent, installation.agent_id)
    version = await db.get(AgentVersion, installation.agent_version_id)
    assert agent and version
    return InstallationOut(
        id=installation.id,
        scope=installation.scope,
        enabled=installation.enabled,
        agent=await _out(db, agent, version),
        created_at=installation.created_at,
        handoff_to=list((version.manifest or {}).get("handoff_to", [])),
        handoff_allow=installation.handoff_allow,
    )


@router.get("/classes/{class_id}/agents", response_model=list[InstallationOut])
async def class_agents(class_id: str, user: CurrentUser, db: DbSession) -> list[InstallationOut]:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    rows = await db.scalars(
        select(Installation)
        .where(Installation.scope == "class", Installation.class_id == room.id)
        .order_by(Installation.created_at)
    )
    return [await _installation_out(db, installation) for installation in rows]


@router.post("/classes/{class_id}/agents", response_model=InstallationOut, status_code=status.HTTP_201_CREATED)
async def install_in_class(class_id: str, payload: InstallIn, user: CurrentUser, db: DbSession) -> InstallationOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    agent, version = await _installable(db, user, payload)
    if agent.slug == FALLBACK_SLUG:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trợ lý lớp luôn có sẵn trong mọi lớp.")
    existing = await db.scalar(
        select(Installation).where(
            Installation.scope == "class", Installation.class_id == room.id, Installation.agent_id == agent.id
        )
    )
    if existing:
        # Re-installing moves the class to the chosen version.
        existing.agent_version_id, existing.enabled = version.id, True
        installation = existing
    else:
        installation = Installation(
            agent_id=agent.id, agent_version_id=version.id, scope="class", class_id=room.id, installed_by=user.id
        )
        db.add(installation)
    await db.commit()
    await db.refresh(installation)
    return await _installation_out(db, installation)


async def _class_installation(db, user: User, class_id: str, installation_id: str) -> Installation:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    installation = await db.get(Installation, installation_id)
    if installation is None or installation.class_id != room.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent trong lớp.")
    return installation


@router.patch("/classes/{class_id}/agents/{installation_id}", response_model=InstallationOut)
async def toggle_class_agent(
    class_id: str, installation_id: str, payload: ToggleIn, user: CurrentUser, db: DbSession
) -> InstallationOut:
    installation = await _class_installation(db, user, class_id, installation_id)
    if payload.enabled is not None:
        installation.enabled = payload.enabled
    if payload.reset_handoffs:
        installation.handoff_allow = None
    elif payload.handoff_allow is not None:
        version = await db.get(AgentVersion, installation.agent_version_id)
        granted = set((version.manifest or {}).get("handoff_to", [])) if version else set()
        extra = [slug for slug in payload.handoff_allow if slug not in granted]
        if extra:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Chỉ thu hẹp được trong các agent người tạo đã cấp quyền: {', '.join(extra)}",
            )
        installation.handoff_allow = list(dict.fromkeys(payload.handoff_allow))
    await db.commit()
    return await _installation_out(db, installation)


@router.delete("/classes/{class_id}/agents/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_class_agent(class_id: str, installation_id: str, user: CurrentUser, db: DbSession) -> None:
    installation = await _class_installation(db, user, class_id, installation_id)
    await db.delete(installation)
    await db.commit()


@router.get("/me/agents", response_model=list[InstallationOut])
async def my_agents(user: CurrentUser, db: DbSession) -> list[InstallationOut]:
    rows = await db.scalars(
        select(Installation)
        .where(Installation.scope == "personal", Installation.user_id == user.id)
        .order_by(Installation.created_at)
    )
    return [await _installation_out(db, installation) for installation in rows]


@router.post("/me/agents", response_model=InstallationOut, status_code=status.HTTP_201_CREATED)
async def install_personal(payload: InstallIn, user: CurrentUser, db: DbSession) -> InstallationOut:
    agent, version = await _installable(db, user, payload)
    manifest = AgentManifest.model_validate(version.manifest)
    if user.role in ("student", "parent") and user.role not in manifest.target_roles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agent này không dành cho vai trò của bạn.")
    existing = await db.scalar(
        select(Installation).where(
            Installation.scope == "personal", Installation.user_id == user.id, Installation.agent_id == agent.id
        )
    )
    if existing:
        existing.agent_version_id = version.id
        installation = existing
    else:
        installation = Installation(
            agent_id=agent.id, agent_version_id=version.id, scope="personal", user_id=user.id, installed_by=user.id
        )
        db.add(installation)
    await db.commit()
    await db.refresh(installation)
    return await _installation_out(db, installation)


@router.delete("/me/agents/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_personal(installation_id: str, user: CurrentUser, db: DbSession) -> None:
    installation = await db.get(Installation, installation_id)
    if installation is None or installation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    await db.delete(installation)
    await db.commit()


# ---------------- Builder ----------------


async def _own_agent(db, user: User, agent_id: str) -> Agent:
    agent = await db.get(Agent, agent_id)
    if (
        agent is None
        or (agent.owner_id != user.id and user.role != Role.ADMIN)
        or agent.is_platform
        and user.role != Role.ADMIN
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    return agent


async def _slug_free(db, slug: str, exclude: str | None = None) -> None:
    query = select(Agent.id).where(Agent.slug == slug)
    if exclude:
        query = query.where(Agent.id != exclude)
    if await db.scalar(query):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mã agent “{slug}” đã được dùng. Hãy chọn mã khác.")


@router.get("/agents/mine", response_model=list[AgentDetailOut])
async def my_built_agents(user: Maker, db: DbSession) -> list[AgentDetailOut]:
    rows = await db.scalars(select(Agent).where(Agent.owner_id == user.id).order_by(Agent.updated_at.desc()))
    return [await hub_detail(agent.id, user, db) for agent in rows]


async def _maker_checks(db, user: User, manifest: AgentManifest) -> None:
    """FR-002, FR-005, FR-006: tools for the maker's role, guardian consent for students, grants to usable agents."""
    if user.role == Role.STUDENT and not await _student_consented(db, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Em cần phụ huynh đồng ý trước khi tạo và dùng agent.")
    if user.role in (Role.STUDENT, Role.PARENT):
        blocked = [tool for tool in manifest.tools if user.role not in TOOLS[tool].roles]
        if blocked:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Công cụ không dành cho vai trò của bạn: {', '.join(blocked)}",
            )
    if manifest.handoff_to:
        allowed = {candidate["slug"] for candidate in await _handoff_candidates(db, user, manifest.slug)}
        wrong = [slug for slug in manifest.handoff_to if slug not in allowed]
        if wrong:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Chỉ cấp quyền giao việc cho agent bạn đang dùng được: {', '.join(wrong)}",
            )


async def _student_consented(db, student_id: str) -> bool:
    return await classes.student_may_use_agents(db, student_id, None)


async def _handoff_candidates(db, user: User, exclude_slug: str | None = None) -> list[dict[str, Any]]:
    """Agents the maker may grant handoffs to: platform agents and certified public agents made for the maker's role
    (any role for teachers), plus the maker's own agents."""
    rows = await db.scalars(
        select(Agent).where(or_(Agent.is_platform.is_(True), Agent.visibility == "public", Agent.owner_id == user.id))
    )
    out = []
    for agent in rows:
        if agent.slug == exclude_slug:
            continue
        own = agent.owner_id == user.id
        version = await latest_version(db, agent.id) if own else await certified_version(db, agent.id)
        if version is None:
            continue
        manifest = AgentManifest.model_validate(version.manifest)
        if user.role in (Role.STUDENT, Role.PARENT) and user.role not in manifest.target_roles:
            continue
        out.append(
            {"slug": agent.slug, "name": manifest.name, "avatar": manifest.avatar, "description": manifest.description}
        )
    return sorted(out, key=lambda item: item["name"])


@router.get("/agents/{agent_id}/handoff-candidates")
async def handoff_candidates(agent_id: str, user: Maker, db: DbSession) -> list[dict[str, Any]]:
    agent = await _own_agent(db, user, agent_id)
    return await _handoff_candidates(db, user, agent.slug)


@router.get("/agents/handoff-candidates")
async def new_agent_handoff_candidates(user: Maker, db: DbSession) -> list[dict[str, Any]]:
    return await _handoff_candidates(db, user)


@router.post("/agents", response_model=AgentDetailOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: ManifestIn, user: Maker, db: DbSession) -> AgentDetailOut:
    manifest = validate_manifest(payload.manifest)
    await _maker_checks(db, user, manifest)
    await _slug_free(db, manifest.slug)
    agent = Agent(
        slug=manifest.slug, owner_id=user.id, visibility="private", draft_manifest=manifest.model_dump(mode="json")
    )
    db.add(agent)
    await db.commit()
    return await hub_detail(agent.id, user, db)


@router.put("/agents/{agent_id}", response_model=AgentDetailOut)
async def update_draft(agent_id: str, payload: ManifestIn, user: Maker, db: DbSession) -> AgentDetailOut:
    agent = await _own_agent(db, user, agent_id)
    manifest = validate_manifest(payload.manifest)
    if manifest.slug != agent.slug:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không đổi được mã agent sau khi tạo.")
    await _maker_checks(db, user, manifest)
    agent.draft_manifest = manifest.model_dump(mode="json")
    await db.commit()
    return await hub_detail(agent.id, user, db)


@router.post("/agents/{agent_id}/versions", response_model=AgentDetailOut, status_code=status.HTTP_201_CREATED)
async def snapshot_version(agent_id: str, user: Maker, db: DbSession) -> AgentDetailOut:
    """Freezes the draft as a new immutable version (uncertified until the pipeline runs on it)."""
    agent = await _own_agent(db, user, agent_id)
    latest = await latest_version(db, agent.id)
    if latest is not None and latest.manifest == agent.draft_manifest:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Bản nháp giống hệt phiên bản {latest.version}.")
    db.add(
        AgentVersion(agent_id=agent.id, version=(latest.version + 1) if latest else 1, manifest=agent.draft_manifest)
    )
    await db.commit()
    return await hub_detail(agent.id, user, db)


@router.post("/agents/{agent_id}/fork", response_model=AgentDetailOut, status_code=status.HTTP_201_CREATED)
async def fork_agent(agent_id: str, user: Maker, db: DbSession) -> AgentDetailOut:
    source, version, _ = await _viewable(db, user, agent_id)
    origin = version.manifest if version else source.draft_manifest
    base = f"{source.slug[:38]}-ban-sao"
    slug, suffix = base, 2
    while await db.scalar(select(Agent.id).where(Agent.slug == slug)):
        slug, suffix = f"{base}-{suffix}", suffix + 1
    manifest = {**origin, "slug": slug, "name": f"{origin['name']} (bản của tôi)"[:80]}
    agent = Agent(slug=slug, owner_id=user.id, visibility="private", forked_from_id=source.id, draft_manifest=manifest)
    db.add(agent)
    await db.commit()
    return await hub_detail(agent.id, user, db)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, user: Maker, db: DbSession) -> None:
    agent = await _own_agent(db, user, agent_id)
    others = await db.scalar(
        select(func.count()).where(
            Installation.agent_id == agent.id,
            or_(Installation.installed_by != user.id, Installation.scope == "personal"),
        )
    )
    if others:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Agent đang được người khác sử dụng; hãy ẩn khỏi Hub thay vì xoá."
        )
    await db.delete(agent)
    await db.commit()


class TryIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    # Role to simulate: the author is a teacher, but the agent may be made for students or parents.
    as_role: Literal["teacher", "student", "parent"] = "student"


@router.post("/agents/{agent_id}/try")
async def try_draft(agent_id: str, payload: TryIn, user: Maker, db: DbSession) -> StreamingResponse:
    """Chats with the current draft outside any class; the run is stored as a sandbox conversation."""
    from app.agents.sandbox import run_sandbox

    agent = await _own_agent(db, user, agent_id)
    if user.role == Role.STUDENT and not await _student_consented(db, user.id):
        # FR-005: the sandbox is still an agent reading the student's messages.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Em cần phụ huynh đồng ý trước khi dùng agent.")
    manifest = validate_manifest(agent.draft_manifest)
    resolved = ResolvedAgent(
        agent_id=agent.id,
        version_id="draft",
        version=0,
        manifest=manifest,
        source="sandbox",
        certification_status="uncertified",
    )
    return StreamingResponse(
        run_sandbox(user.id, resolved, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AgentRequestIn(BaseModel):
    agent_id: str


@router.post("/classes/{class_id}/agent-requests", status_code=status.HTTP_201_CREATED)
async def request_agent_in_class(class_id: str, payload: AgentRequestIn, user: CurrentUser, db: DbSession):
    """A student or parent asks to add their own agent to the class (FR-003): sharing is an always-ask action, the
    agent needs a certified version, and the homeroom teacher decides in their inbox."""
    from datetime import UTC, datetime, timedelta

    from app.chat.direct import open_direct
    from app.config import get_settings
    from app.orchestration import approvals, people
    from app.orchestration.models import PersonRequest

    room, role = await classes.load_class(db, class_id, user, {"student", "parent"})
    if not (room.policy or {}).get("allow_member_agents", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Lớp này chưa cho đưa agent tự tạo vào lớp.")
    agent = await db.get(Agent, payload.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy agent.")
    version = await certified_version(db, agent.id)
    if version is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agent cần qua kiểm định trước khi đưa vào lớp.")
    manifest = AgentManifest.model_validate(version.manifest)
    conversation = await open_direct(db, user, room, None, title="Trợ lý")
    request = PersonRequest(
        conversation_id=conversation.id,
        class_id=room.id,
        requester_id=user.id,
        agent_slug=FALLBACK_SLUG,
        recipient_id=room.owner_id,
        kind="install_agent",
        body=f"{user.name} xin đưa agent “{manifest.name}” (đã kiểm định) vào lớp {room.name}. {manifest.description}",
        options=["Đồng ý", "Từ chối"],
        payload={"agent_id": agent.id, "version_id": version.id},
        status="draft",
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().person_request_hours),
    )
    db.add(request)
    await db.flush()
    action = approvals.Action("share", FALLBACK_SLUG, "install_agent", room.id)
    decision = await approvals.decide_for(
        db, action, user_id=user.id, role=role, class_id=room.id, conversation_id=conversation.id
    )
    if decision.effect == "deny":
        request.status = "cancelled"
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Việc chia sẻ agent bị chặn bởi quy tắc duyệt.")
    if decision.effect == "allow":
        await people.open_request(db, request)
        await db.commit()
        return {"status": "sent", "request_id": request.id, "conversation_id": conversation.id}
    card = await approvals.open_card(
        db,
        run_id=None,
        tool_call_id=f"install-{request.id}",
        conversation_id=conversation.id,
        user_id=user.id,
        action=approvals.Action("share", FALLBACK_SLUG, "ask_person", room.id),
        arguments={"request_id": request.id},
        summary=f"Xin giáo viên chủ nhiệm đưa “{manifest.name}” vào lớp {room.name}",
        preview={"body": request.body, "targets": [{"id": room.owner_id, "name": "", "role_label": "GV chủ nhiệm"}]},
        choices=decision.choices,
    )
    await db.commit()
    return {"status": "waiting_approval", "card_id": card.id, "conversation_id": conversation.id}


@router.get("/agents/{agent_id}/activity")
async def agent_activity_page(agent_id: str, user: Maker, db: DbSession) -> list[dict[str, Any]]:
    """The agent's activity for its owner (FR-057): runs, handoffs and refusals with their reasons, no conversation
    text of other people."""
    from app.orchestration.activity import agent_activity

    agent = await _own_agent(db, user, agent_id)
    return await agent_activity(db, agent.slug)
