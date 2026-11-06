from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError, forbidden, unauthorized
from app.core.security import decode_access_token
from app.models import User
from app.services.auth_service import session_is_active

bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session_id: UUID


def _authenticate(credentials: HTTPAuthorizationCredentials, db: Session) -> AuthContext:
    invalid = unauthorized("Invalid or expired access token.")
    try:
        user_id, session_id = decode_access_token(credentials.credentials)
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise invalid from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active or not session_is_active(db, user_id, session_id):
        raise invalid
    return AuthContext(user, session_id)


def get_auth_context(credentials: Credentials, db: DatabaseSession) -> AuthContext:
    if credentials is None:
        raise unauthorized()
    return _authenticate(credentials, db)


Auth = Annotated[AuthContext, Depends(get_auth_context)]


def get_current_user(context: Auth) -> User:
    return context.user


def get_optional_user(credentials: Credentials, db: DatabaseSession) -> User | None:
    """Public routes: no token means guest, but a bad token is still an error rather than a silent downgrade."""
    return None if credentials is None else _authenticate(credentials, db).user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*roles: str):
    def checker(user: CurrentUser) -> User:
        if not user.has_role(*roles):
            raise forbidden()
        return user

    return Depends(checker)


AdminUser = Annotated[User, require_roles("admin")]
ReviewerUser = Annotated[User, require_roles("verifier", "admin")]
OwnerUser = Annotated[User, require_roles("owner", "admin")]


def require_csrf_header(request: Request) -> None:
    """Cookie-authenticated routes need a header that cross-site forms cannot set."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise AppError(403, "csrf_required", "Missing required request header.")


CsrfProtected = Depends(require_csrf_header)


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int


def pagination(page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100)) -> Pagination:
    return Pagination(page, page_size)


Paging = Annotated[Pagination, Depends(pagination)]
