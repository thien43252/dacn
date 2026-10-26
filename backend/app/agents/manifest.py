"""The agent contract: a declarative manifest. Agents never ship code; they pick tools from the platform registry."""

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

AgentRole = Literal["teacher", "student", "parent"]
Knowledge = Literal["class_documents", "none"]
# Must match the mascot sheets in web/src/components/Mascot.tsx.
MASCOTS = {
    "fox",
    "cat",
    "panda",
    "penguin",
    "owl",
    "bear",
    "bunny",
    "deer",
    "frog",
    "hamster",
    "hedgehog",
    "koala",
    "otter",
    "raccoon",
    "redpanda",
}
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FALLBACK_SLUG = "tro-ly-lop"


class Example(BaseModel):
    user: str = Field(max_length=500)
    assistant: str = Field(max_length=1500)


class AgentManifest(BaseModel):
    slug: str = Field(min_length=3, max_length=48)
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=500)
    avatar: str = "owl"
    subjects: list[str] = Field(default_factory=lambda: ["chung"], max_length=11)
    grades: list[int] = Field(default_factory=list, max_length=12)
    target_roles: list[AgentRole] = Field(min_length=1)
    age_range: tuple[int, int] | None = None
    # Short phrases the orchestrator matches requests against ("giải thích khái niệm toán", "luyện nói tiếng Anh").
    capabilities: list[str] = Field(min_length=1, max_length=12)
    tools: list[str] = Field(default_factory=list, max_length=10)
    knowledge: Knowledge = "none"
    system_prompt: str = Field(min_length=40, max_length=8000)
    examples: list[Example] = Field(default_factory=list, max_length=5)
    starter_prompts: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError("Mã agent chỉ gồm chữ thường không dấu, số và dấu gạch ngang.")
        return value

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, value: str) -> str:
        return value if value in MASCOTS else "owl"

    @field_validator("grades")
    @classmethod
    def _grades(cls, value: list[int]) -> list[int]:
        if any(not 1 <= grade <= 12 for grade in value):
            raise ValueError("Khối lớp phải từ 1 đến 12.")
        return sorted(set(value))

    @model_validator(mode="after")
    def _ages(self) -> "AgentManifest":
        if self.age_range and not (5 <= self.age_range[0] <= self.age_range[1] <= 99):
            raise ValueError("Độ tuổi không hợp lệ.")
        return self


def load_manifest_file(path: Path) -> AgentManifest:
    with path.open(encoding="utf-8") as handle:
        return AgentManifest.model_validate(yaml.safe_load(handle))


def builtin_manifests(seed_dir: Path) -> dict[str, AgentManifest]:
    return {manifest.slug: manifest for manifest in map(load_manifest_file, sorted(seed_dir.glob("*.yaml")))}
