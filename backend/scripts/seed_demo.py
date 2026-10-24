"""Create the demo accounts shown on the login page. Idempotent: existing emails are left untouched.

Usage (from backend/): uv run python -m scripts.seed_demo
"""

import asyncio

from app.auth.models import Role
from app.auth.service import EmailTakenError, create_user
from app.db import dispose_engine, get_session

DEMO_PASSWORD = "Demo123!"
DEMO_ACCOUNTS = [
    ("Cô Nguyễn Thu Hà", "teacher@demo.edu.vn", Role.TEACHER),
    ("Nguyễn Minh Anh", "student@demo.edu.vn", Role.STUDENT),
    ("Nguyễn Văn Bình", "parent@demo.edu.vn", Role.PARENT),
    ("Quản trị viên", "admin@demo.edu.vn", Role.ADMIN),
]


async def main() -> None:
    async for db in get_session():
        for name, email, role in DEMO_ACCOUNTS:
            try:
                await create_user(db, name=name, email=email, password=DEMO_PASSWORD, role=role)
                print(f"created {role.value:8} {email}")
            except EmailTakenError:
                print(f"exists  {role.value:8} {email}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
