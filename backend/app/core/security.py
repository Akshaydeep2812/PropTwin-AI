import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()
# Verified against when the account does not exist, so response timing does not reveal registered emails.
_DUMMY_HASH = password_hash.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def burn_password_check(password: str) -> None:
    password_hash.verify(password, _DUMMY_HASH)


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str) -> tuple[UUID, UUID]:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["sub", "sid", "exp"]},
    )
    return UUID(payload["sub"]), UUID(payload["sid"])


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
