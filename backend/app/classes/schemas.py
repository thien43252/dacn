from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Subject = Literal["toan", "van", "anh", "ly", "hoa", "sinh", "su", "dia", "gdcd", "tin", "khac"]
ClassRole = Literal["teacher", "student", "parent"]


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not 2 <= len(value) <= 120:
        raise ValueError("Tên lớp cần có từ 2 đến 120 ký tự.")
    return value


class ClassIn(BaseModel):
    name: str
    subject: Subject
    grade: int = Field(ge=1, le=12)
    description: str = Field(default="", max_length=2000)
    require_parent_consent: bool = True

    _name = field_validator("name")(_clean_name)


class ClassPatch(BaseModel):
    name: str | None = None
    subject: Subject | None = None
    grade: int | None = Field(default=None, ge=1, le=12)
    description: str | None = Field(default=None, max_length=2000)
    require_parent_consent: bool | None = None
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class ClassOut(BaseModel):
    id: str
    name: str
    subject: str
    grade: int
    description: str
    teacher_name: str
    my_role: ClassRole
    student_count: int
    require_parent_consent: bool
    archived: bool
    created_at: datetime
    # Only the class's teachers see the join code.
    join_code: str | None = None
    # For a parent: which of their children are in the class.
    children: list[str] = []


class PolicyModel(BaseModel):
    no_direct_answers: bool = True
    allowed_subjects: list[str] = Field(default_factory=list, max_length=20)
    blocked_topics: list[str] = Field(default_factory=list, max_length=50)
    allow_personal_agents: bool = True
    notes_for_agents: str = Field(default="", max_length=1000)


class JoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class AddMemberIn(BaseModel):
    email: str


class LinkParentIn(BaseModel):
    parent_email: str
    student_id: str


class PersonOut(BaseModel):
    id: str
    name: str
    email: str


class ConsentOut(BaseModel):
    allow_agents: bool
    allow_progress_reports: bool
    updated_at: datetime | None = None


class MemberOut(BaseModel):
    user_id: str
    name: str
    email: str
    role: Literal["teacher", "student"]
    joined_at: datetime
    parents: list[PersonOut] = []
    # True when the class does not need consent, or a linked parent allowed agents.
    can_use_agents: bool


class ChildClassOut(BaseModel):
    id: str
    name: str
    subject: str
    grade: int
    teacher_name: str


class ChildOut(BaseModel):
    id: str
    name: str
    email: str
    classes: list[ChildClassOut]
    consent: ConsentOut


class LinkCodeOut(BaseModel):
    code: str
    parents: list[PersonOut]


class LinkChildIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class ConsentIn(BaseModel):
    allow_agents: bool
    allow_progress_reports: bool = True
