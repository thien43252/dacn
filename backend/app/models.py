"""Imports every module's ORM models so `Base.metadata` is complete for Alembic and tests.

Add one import line here whenever a module gains a `models.py`.
"""

from app.agents import models as agents_models  # noqa: F401,E402
from app.audit import models as audit_models  # noqa: F401,E402
from app.auth import models as auth_models  # noqa: F401,E402
from app.certify import models as certify_models  # noqa: F401,E402
from app.chat import models as chat_models  # noqa: F401,E402
from app.classes import models as classes_models  # noqa: F401,E402
from app.knowledge import models as knowledge_models  # noqa: F401,E402
