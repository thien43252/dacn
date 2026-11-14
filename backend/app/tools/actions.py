"""Teacher tools that act outside the conversation and run only after the user confirms (specs/002-multi-agent-
orchestration research R18, contracts/mcp-tools.md, FR-047 to FR-050).

The tool guard never runs these when an agent calls them: it screens what would be shared (6b), builds the preview
below and asks the user. After "Đồng ý" the orchestrator calls `execute_*` directly with the exact arguments the user
saw, once. Previews are built by code from the arguments, never written by a model (FR-048).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select

from app.agents import service as agents
from app.agents.manifest import AgentManifest
from app.agents.models import Agent
from app.auth.models import User
from app.class_feed.models import Assignment, ClassAnnouncement
from app.classes.models import ClassMember, ClassRoom, ParentLink
from app.db import session_factory
from app.knowledge import service as knowledge

if TYPE_CHECKING:
    from app.tools.registry import ToolContext

PREVIEW_CHARS = 600
NOTES_MAX = 1000
AUDIENCE_LABELS = {"students": "học sinh", "parents": "phụ huynh", "all": "học sinh và phụ huynh"}


class ActionFailure(Exception):
    """A user-facing reason a confirmed action could not run."""


# ---------- Arguments ----------


class SaveDocumentArgs(BaseModel):
    title: str = Field(min_length=3, max_length=120, description="Tên tài liệu")
    content: str = Field(min_length=20, max_length=20000, description="Nội dung Markdown của tài liệu")


class AgentNotesArgs(BaseModel):
    notes: str = Field(max_length=NOTES_MAX, description="Ghi chú cho mọi agent của lớp")
    mode: Literal["replace", "append"] = Field(default="append", description="Thay hẳn hay thêm vào ghi chú cũ")


class InstallAgentArgs(BaseModel):
    agent: str = Field(min_length=2, max_length=48, description="Slug của agent trên Hub")


class AnnouncementArgs(BaseModel):
    title: str = Field(min_length=3, max_length=120, description="Tiêu đề thông báo")
    body: str = Field(min_length=10, max_length=2000, description="Nội dung thông báo")
    audience: Literal["students", "parents", "all"] = Field(default="students", description="Ai nhận thông báo")


class PracticeQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=6)


class AnswerKeyItem(BaseModel):
    index: int = Field(ge=1, le=20)
    answer: str = Field(max_length=500)
    explanation: str = Field(default="", max_length=1000)


class PracticeArgs(BaseModel):
    title: str = Field(min_length=3, max_length=120, description="Tên bài luyện")
    instructions: str = Field(default="", max_length=1000, description="Hướng dẫn làm bài")
    questions: list[PracticeQuestion] = Field(min_length=1, max_length=20, description="Các câu hỏi")
    answer_key: list[AnswerKeyItem] | None = Field(default=None, description="Đáp án, chỉ giáo viên thấy")
    due_at: datetime | None = Field(default=None, description="Hạn nộp, ISO 8601")


TEACHER_TOOLS = {"save_class_document", "set_agent_notes", "install_agent", "post_class_announcement", "assign_practice"}


def shared_text(name: str, args: BaseModel) -> str:
    """Every text field other people will read, for the keyword check and the share review (6b). The answer key is
    never sent to review."""
    if isinstance(args, SaveDocumentArgs):
        return f"{args.title}\n{args.content}"
    if isinstance(args, AgentNotesArgs):
        return args.notes
    if isinstance(args, AnnouncementArgs):
        return f"{args.title}\n{args.body}"
    if isinstance(args, PracticeArgs):
        lines = [args.title, args.instructions]
        for item in args.questions:
            lines.append(item.question)
            lines.extend(item.options)
        return "\n".join(line for line in lines if line)
    return ""


def keyword_text(name: str, args: BaseModel) -> str:
    """The keyword check covers the answer key too: it is stored and shown to teachers."""
    text = shared_text(name, args)
    if isinstance(args, PracticeArgs) and args.answer_key:
        text += "\n" + "\n".join(f"{item.answer}\n{item.explanation}" for item in args.answer_key)
    return text


# ---------- Shared helpers ----------


async def is_class_teacher(user_id: str, class_id: str | None) -> bool:
    """Step 6a: a teacher of this class, not just any teacher."""
    if not class_id:
        return False
    async with session_factory()() as db:
        room = await db.get(ClassRoom, class_id)
        if room is None:
            return False
        if room.owner_id == user_id:
            return True
        role = await db.scalar(
            select(ClassMember.role).where(ClassMember.class_id == class_id, ClassMember.user_id == user_id)
        )
        return role == "teacher"


async def _students(db, class_id: str) -> int:
    return (
        await db.scalar(
            select(func.count()).where(ClassMember.class_id == class_id, ClassMember.role == "student")
        )
        or 0
    )


async def _parents(db, class_id: str) -> int:
    students = select(ClassMember.user_id).where(ClassMember.class_id == class_id, ClassMember.role == "student")
    return (
        await db.scalar(select(func.count(distinct(ParentLink.parent_id))).where(ParentLink.student_id.in_(students)))
        or 0
    )


async def _room(db, ctx: "ToolContext") -> ClassRoom:
    room = await db.get(ClassRoom, ctx.class_id) if ctx.class_id else None
    if room is None:
        raise ActionFailure("Không tìm thấy lớp.")
    return room


def _head(text: str) -> str:
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"


def _link(class_id: str, tab: str) -> str:
    return f"/classes/{class_id}?tab={tab}"


async def _hub_agent(db, slug: str) -> tuple[Agent, AgentManifest] | None:
    agent = await db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is None:
        return None
    version = await agents.certified_version(db, agent.id) or await agents.latest_version(db, agent.id)
    manifest = AgentManifest.model_validate(version.manifest) if version else None
    return (agent, manifest) if manifest else None


def _new_notes(old: str, args: AgentNotesArgs) -> str:
    if args.mode == "replace" or not old.strip():
        return args.notes.strip()[:NOTES_MAX]
    return f"{old.rstrip()}\n{args.notes.strip()}"[:NOTES_MAX]


# ---------- Previews (FR-048) ----------


async def preview(name: str, ctx: "ToolContext", args: BaseModel) -> dict[str, Any]:
    """{summary, impact, audience_count, preview} for the confirmation card, built from the arguments."""
    async with session_factory()() as db:
        room = await _room(db, ctx)
        if isinstance(args, SaveDocumentArgs):
            students = await _students(db, room.id)
            return {
                "summary": f"Lưu “{args.title}” vào tài liệu lớp {room.name}.",
                "impact": "Học sinh và các agent của lớp sẽ đọc được.",
                "audience_count": students,
                "preview": {"title": args.title, "body": _head(args.content)},
            }
        if isinstance(args, AgentNotesArgs):
            old = str((room.policy or {}).get("notes_for_agents", ""))
            return {
                "summary": f"Đổi ghi chú cho mọi agent của lớp {room.name}.",
                "impact": "Mọi agent trong lớp sẽ làm theo ghi chú mới từ tin nhắn tiếp theo.",
                "audience_count": None,
                "preview": {"before": old, "after": _new_notes(old, args)},
            }
        if isinstance(args, InstallAgentArgs):
            found = await _hub_agent(db, args.agent)
            if found is None:
                raise ActionFailure(f"Không tìm thấy agent “{args.agent}” trên Hub.")
            _, manifest = found
            students = await _students(db, room.id)
            return {
                "summary": f"Cài agent “{manifest.name}” vào lớp {room.name}; {students} học sinh sẽ dùng được.",
                "impact": "Gỡ lại được ở tab Agent của lớp.",
                "audience_count": students,
                "preview": {"title": manifest.name, "body": manifest.description},
            }
        if isinstance(args, AnnouncementArgs):
            students = await _students(db, room.id) if args.audience in ("students", "all") else 0
            parents = await _parents(db, room.id) if args.audience in ("parents", "all") else 0
            count = students + parents
            return {
                "summary": (
                    f"Đăng thông báo “{args.title}” tới {AUDIENCE_LABELS[args.audience]} lớp {room.name} ({count} người)."
                ),
                "impact": "Người nhận thấy thông báo ngay trên trang lớp. Xoá lại được ở tab Bảng tin.",
                "audience_count": count,
                "preview": {"title": args.title, "body": _head(args.body)},
            }
        if isinstance(args, PracticeArgs):
            students = await _students(db, room.id)
            due = args.due_at.strftime("%H:%M %d/%m/%Y") if args.due_at else "không có hạn"
            return {
                "summary": (
                    f"Giao bài “{args.title}” ({len(args.questions)} câu) cho {students} học sinh lớp {room.name}, "
                    f"hạn {due}."
                ),
                "impact": "Học sinh thấy bài trên trang lớp, không thấy đáp án. Xoá lại được ở tab Bảng tin.",
                "audience_count": students,
                "preview": {"title": args.title, "body": args.instructions, "items": [q.question for q in args.questions]},
            }
    raise ActionFailure("Công cụ không có phần xem trước.")


# ---------- Running after confirmation ----------


async def execute(name: str, ctx: "ToolContext", args: BaseModel, run_id: str | None = None) -> dict[str, Any]:
    """Runs a confirmed action. Returns {done, summary, link, result_ref}."""
    async with session_factory()() as db:
        room = await _room(db, ctx)
        if isinstance(args, SaveDocumentArgs):
            document = await knowledge.create_text_document(db, room, ctx.user_id, args.title, args.content)
            return {
                "done": True,
                "summary": f"Đã lưu “{document.title}” vào tài liệu lớp; đang đồng bộ cho các agent.",
                "link": _link(room.id, "documents"),
                "result_ref": document.id,
            }
        if isinstance(args, AgentNotesArgs):
            policy = dict(room.policy or {})
            policy["notes_for_agents"] = _new_notes(str(policy.get("notes_for_agents", "")), args)
            room.policy = policy
            await db.commit()
            return {
                "done": True,
                "summary": "Đã cập nhật ghi chú cho agent của lớp.",
                "link": _link(room.id, "policy"),
                "result_ref": room.id,
            }
        if isinstance(args, InstallAgentArgs):
            found = await _hub_agent(db, args.agent)
            user = await db.get(User, ctx.user_id)
            if found is None or user is None:
                raise ActionFailure(f"Không tìm thấy agent “{args.agent}” trên Hub.")
            agent, manifest = found
            try:
                installation, already = await agents.install_in_class(db, room, user, agent.id, move=False)
            except agents.InstallError as error:
                raise ActionFailure(error.message) from error
            summary = (
                f"Agent “{manifest.name}” đã có sẵn trong lớp." if already else f"Đã cài agent “{manifest.name}” vào lớp."
            )
            return {"done": True, "summary": summary, "link": _link(room.id, "agents"), "result_ref": installation.id}
        if isinstance(args, AnnouncementArgs):
            row = ClassAnnouncement(
                class_id=room.id,
                author_id=ctx.user_id,
                title=args.title.strip(),
                body=args.body.strip(),
                audience=args.audience,
                source="agent",
                run_id=run_id,
            )
            db.add(row)
            await db.commit()
            return {
                "done": True,
                "summary": f"Đã đăng thông báo “{row.title}”.",
                "link": _link(room.id, "feed"),
                "result_ref": row.id,
            }
        if isinstance(args, PracticeArgs):
            row = Assignment(
                class_id=room.id,
                author_id=ctx.user_id,
                title=args.title.strip(),
                instructions=args.instructions.strip(),
                questions=[q.model_dump() for q in args.questions],
                answer_key=[item.model_dump() for item in args.answer_key] if args.answer_key else None,
                due_at=args.due_at,
                source="agent",
                run_id=run_id,
            )
            db.add(row)
            await db.commit()
            return {
                "done": True,
                "summary": f"Đã giao bài “{row.title}” ({len(args.questions)} câu).",
                "link": _link(room.id, "feed"),
                "result_ref": row.id,
            }
    raise ActionFailure("Công cụ không chạy được.")
