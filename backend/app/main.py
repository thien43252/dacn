from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.config import get_settings
from app.db import dispose_engine, ping_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
    app.include_router(api)
    return app


app = create_app()
