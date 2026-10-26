import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.router import router as agents_router
from app.agents.service import sync_platform_agents
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.certify.pipeline import fail_interrupted
from app.certify.router import router as certify_router
from app.chat.router import router as chat_router
from app.classes.router import router as classes_router
from app.config import get_settings
from app.db import dispose_engine, ping_database, session_factory
from app.knowledge.router import router as documents_router
from app.reports.router import router as reports_router
from app.tools.router import router as tools_router

log = logging.getLogger("eduagent")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        async with session_factory()() as db:
            changed = await sync_platform_agents(db)
            interrupted = await fail_interrupted(db)
        if changed:
            log.info("platform agents updated: %s", ", ".join(changed))
        if interrupted:
            log.warning("%d interrupted certification runs marked failed", interrupted)
    except Exception:  # the API still starts (health checks work) when the database is down
        log.exception("could not sync platform agents")
    yield
    await dispose_engine()


async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """The web client shows `detail` as one string, so the first validator message is surfaced as-is."""
    errors = exc.errors()
    message = "Dữ liệu gửi lên không hợp lệ."
    if errors:
        raw = str(errors[0].get("msg", ""))
        # Pydantic prefixes custom ValueError messages with "Value error, ".
        message = raw.removeprefix("Value error, ") if raw.startswith("Value error, ") else message
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": message, "errors": jsonable_encoder(errors)},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="EduAgent Hub API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(RequestValidationError, validation_error)

    api = APIRouter(prefix="/api")

    @api.get("/health")
    async def health() -> dict[str, str]:
        """Liveness: the process is up. Does not touch the database."""
        return {"status": "ok"}

    @api.get("/health/ready")
    async def ready() -> dict[str, str]:
        """Readiness: the database answers."""
        database_up = await ping_database()
        return {"status": "ok" if database_up else "degraded", "database": "up" if database_up else "down"}

    api.include_router(auth_router)
    api.include_router(classes_router)
    api.include_router(chat_router)
    api.include_router(agents_router)
    api.include_router(documents_router)
    api.include_router(audit_router)
    api.include_router(certify_router)
    api.include_router(reports_router)
    api.include_router(tools_router)
    app.include_router(api)
    return app


app = create_app()
