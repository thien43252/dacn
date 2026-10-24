from fastapi import APIRouter, HTTPException, Request, Response, status

from app.auth.deps import CurrentUser, DbSession
from app.auth.models import Role
from app.auth.schemas import AuthResponse, LoginIn, RegisterIn, UserOut
from app.auth.service import EmailTakenError, authenticate, create_user, end_session, start_session
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, response: Response, db: DbSession) -> AuthResponse:
    try:
        user = await create_user(
            db, name=payload.name, email=payload.email, password=payload.password, role=Role(payload.role)
        )
    except EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email này đã được đăng ký.") from None
    _set_cookie(response, await start_session(db, user, get_settings().session_hours))
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginIn, response: Response, db: DbSession) -> AuthResponse:
    user = await authenticate(db, payload.email, payload.password)
    if user is None:
        # One message for unknown email and wrong password, so accounts cannot be enumerated.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng.")
    _set_cookie(response, await start_session(db, user, get_settings().session_hours))
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/logout")
async def logout(request: Request, response: Response, db: DbSession) -> dict[str, bool]:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await end_session(db, token)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/session", response_model=AuthResponse)
async def session(user: CurrentUser) -> AuthResponse:
    return AuthResponse(user=UserOut.model_validate(user))
