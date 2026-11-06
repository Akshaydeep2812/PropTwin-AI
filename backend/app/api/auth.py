from fastapi import APIRouter, Cookie, Request, Response, status
from sqlalchemy import select

from app.api.dependencies import CsrfProtected, CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.core.errors import not_found, unauthorized
from app.core.rate_limit import limiter
from app.models import User
from app.schemas.auth import (
    DemoAccount,
    DemoLoginRequest,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    TokenConfirm,
    TokenResponse,
    UserCreate,
    UserRead,
)
from app.services import audit, auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE = "proptwin_refresh"
COOKIE_PATH = "/api/v1/auth"


def _set_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )


def _token_response(user, access: str) -> TokenResponse:
    return TokenResponse(access_token=access, expires_in=get_settings().access_token_minutes * 60, user=UserRead.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, response: Response, payload: UserCreate, db: DatabaseSession) -> TokenResponse:
    user = auth_service.register_user(db, str(payload.email), payload.password, payload.display_name, payload.role)
    access, raw = auth_service.start_session(db, user)
    db.commit()
    _set_cookie(response, raw)
    return _token_response(user, access)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: DatabaseSession) -> TokenResponse:
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    access, raw = auth_service.start_session(db, user)
    db.commit()
    _set_cookie(response, raw)
    return _token_response(user, access)


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts(db: DatabaseSession) -> list[User]:
    """Empty unless DEMO_LOGIN_ENABLED is on, so that the sign-in page simply shows no demo buttons."""
    if not get_settings().demo_login_enabled or get_settings().is_production:
        return []
    return list(db.scalars(select(User).where(User.is_demo.is_(True), User.is_active.is_(True)).order_by(User.email)))


@router.post("/demo-login", response_model=TokenResponse)
@limiter.limit("10/minute")
def demo_login(request: Request, response: Response, payload: DemoLoginRequest, db: DatabaseSession) -> TokenResponse:
    # Only accounts the seed script flagged as demo qualify. Any other account answers exactly as if it did not exist.
    user = None
    if get_settings().demo_login_enabled and not get_settings().is_production:
        user = db.scalar(select(User).where(User.email == str(payload.email).lower(), User.is_demo.is_(True), User.is_active.is_(True)))
    if user is None:
        raise not_found("Demo account")
    access_token, raw = auth_service.start_session(db, user)
    audit.record(db, "auth.demo_login", "user", user.id, actor_id=user.id)
    db.commit()
    _set_cookie(response, raw)
    return _token_response(user, access_token)


@router.post("/refresh", response_model=TokenResponse, dependencies=[CsrfProtected])
@limiter.limit("120/minute")  # Every full page load refreshes, and the 256-bit token itself cannot be guessed.
def refresh(
    request: Request,
    response: Response,
    db: DatabaseSession,
    proptwin_refresh: str | None = Cookie(default=None),
) -> TokenResponse:
    if not proptwin_refresh:
        raise unauthorized("The session is invalid or has expired.")
    user, access, raw = auth_service.rotate_session(db, proptwin_refresh)
    db.commit()
    _set_cookie(response, raw)
    return _token_response(user, access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CsrfProtected])
def logout(db: DatabaseSession, proptwin_refresh: str | None = Cookie(default=None)) -> Response:
    if proptwin_refresh:
        auth_service.revoke_by_raw_token(db, proptwin_refresh)
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, db: DatabaseSession) -> Response:
    auth_service.revoke_all_sessions(db, user.id)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/password-reset/request", response_model=MessageResponse)
@limiter.limit("5/minute")
def request_password_reset(request: Request, payload: EmailRequest, db: DatabaseSession) -> MessageResponse:
    auth_service.request_password_reset(db, str(payload.email))
    return MessageResponse(message="If that account exists, a reset link has been issued.")


@router.post("/password-reset/confirm", response_model=MessageResponse)
@limiter.limit("10/minute")
def confirm_password_reset(request: Request, payload: PasswordResetConfirm, db: DatabaseSession) -> MessageResponse:
    auth_service.confirm_password_reset(db, payload.token, payload.new_password)
    return MessageResponse(message="Password updated. Sign in with your new password.")


@router.post("/email-verification/request", response_model=MessageResponse)
@limiter.limit("5/minute")
def request_email_verification(request: Request, user: CurrentUser, db: DatabaseSession) -> MessageResponse:
    delivery = auth_service.request_email_verification(db, user)
    message = "Verification email sent." if delivery == "sent" else "Email delivery is not configured on this server."
    return MessageResponse(message=message, delivery=delivery)


@router.post("/email-verification/confirm", response_model=MessageResponse)
@limiter.limit("10/minute")
def confirm_email_verification(request: Request, payload: TokenConfirm, db: DatabaseSession) -> MessageResponse:
    auth_service.confirm_email_verification(db, payload.token)
    return MessageResponse(message="Email verified.")
