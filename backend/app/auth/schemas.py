import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_PATTERN.match(value):
        raise ValueError("Nhập email đúng định dạng.")
    return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: Literal["teacher", "student", "parent", "admin"]


class AuthResponse(BaseModel):
    user: UserOut


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1)

    _email = field_validator("email")(_normalize_email)


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    # Admin accounts are seeded, never self-registered.
    role: Literal["teacher", "student", "parent"]

    _email = field_validator("email")(_normalize_email)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not 2 <= len(value) <= 120:
            raise ValueError("Tên cần có từ 2 đến 120 ký tự.")
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        # Mirrors web/src/auth/validation.ts so both sides reject the same input.
        has_classes = all(re.search(pattern, value) for pattern in (r"[A-Z]", r"[a-z]", r"\d"))
        if len(value) < 8 or not has_classes:
            raise ValueError("Dùng ít nhất 8 ký tự, gồm chữ hoa, chữ thường và số.")
        return value
