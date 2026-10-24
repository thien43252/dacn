"""Imports every module's ORM models so `Base.metadata` is complete for Alembic and tests.

Add one import line here whenever a module gains a `models.py`.
"""

from app.auth import models as auth_models  # noqa: F401,E402
