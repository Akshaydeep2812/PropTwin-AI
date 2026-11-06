import secrets
import uuid
from datetime import timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3

from app.core.config import get_settings
from app.core.errors import AppError, conflict, unauthorized
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.models import AccountToken, RefreshToken, Role, User
from app.models.types import utcnow
from app.services import audit
from app.services.email import send_email

TOKEN_LIFETIMES = {"verify_email": timedelta(days=2), "reset_password": timedelta(hours=1)}
ROTATION_GRACE = timedelta(seconds=10)


def get_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def register_user(db: Session, email: str, password: str, display_name: str, role: str) -> User:
    normalized = email.lower()
    if db.scalar(select(User.id).where(User.email == normalized)):
        raise conflict("email_taken", "An account with this email already exists.")
    user = User(email=normalized, password_hash=hash_password(password), display_name=display_name)
    user.roles.append(get_role(db, role))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("email_taken", "An account with this email already exists.") from exc
    audit.record(db, "user.registered", "user", user.id, actor_id=user.id, role=role)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        burn_password_check(password)
    elif verify_password(password, user.password_hash) and user.is_active:
        audit.record(db, "user.login", "user", user.id, actor_id=user.id)
        return user
    audit.record(db, "user.login_failed", "user", None if user is None else user.id)
    db.commit()
    raise AppError(401, "invalid_credentials", "Invalid email or password.", {"WWW-Authenticate": "Bearer"})


def start_session(db: Session, user: User, family_id: uuid.UUID | None = None) -> tuple[str, str]:
    """Returns (access token, raw refresh token). Only the refresh token's hash is stored."""
    settings = get_settings()
    family = family_id or uuid.uuid4()
    raw = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family,
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    return create_access_token(user.id, family), raw


def rotate_session(db: Session, raw_token: str) -> tuple[User, str, str]:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update())
    if token is None:
        raise unauthorized("The session is invalid or has expired.")
    now = utcnow()
    if token.revoked_at is not None or token.expires_at <= now:
        raise unauthorized("The session is invalid or has expired.")
    if token.rotated_at is not None and now - token.rotated_at > ROTATION_GRACE:
        # A long-rotated token came back: it was stolen or replayed, so end the whole session family.
        revoke_family(db, token.family_id)
        audit.record(db, "session.reuse_detected", "user", token.user_id, actor_id=token.user_id)
        db.commit()
        raise unauthorized("The session is invalid or has expired.")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise unauthorized("The session is invalid or has expired.")
    # Inside the grace window this is two tabs refreshing together, not theft, so both get a working session.
    if token.rotated_at is None:
        token.rotated_at = now
    access, raw = start_session(db, user, token.family_id)
    return user, access, raw


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))


def revoke_by_raw_token(db: Session, raw_token: str) -> None:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if token is not None:
        revoke_family(db, token.family_id)
        audit.record(db, "user.logout", "user", token.user_id, actor_id=token.user_id)


def revoke_all_sessions(db: Session, user_id: uuid.UUID, except_family: uuid.UUID | None = None) -> None:
    statement = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if except_family is not None:
        statement = statement.where(RefreshToken.family_id != except_family)
    db.execute(statement.values(revoked_at=utcnow()))


def session_is_active(db: Session, user_id: uuid.UUID, family_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(RefreshToken.id)
            .where(RefreshToken.user_id == user_id, RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .limit(1)
        )
        is not None
    )


def _issue_account_token(db: Session, user: User, purpose: str) -> str:
    raw = new_opaque_token()
    db.add(AccountToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=utcnow() + TOKEN_LIFETIMES[purpose]))
    return raw


def _consume_account_token(db: Session, raw: str, purpose: str) -> User:
    token = db.scalar(
        select(AccountToken).where(AccountToken.token_hash == hash_token(raw), AccountToken.purpose == purpose).with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at <= utcnow():
        raise AppError(400, "invalid_token", "This link is invalid or has expired.")
    token.used_at = utcnow()
    user = db.get(User, token.user_id)
    if user is None:
        raise AppError(400, "invalid_token", "This link is invalid or has expired.")
    return user


def request_password_reset(db: Session, email: str) -> None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active:
        return
    raw = _issue_account_token(db, user, "reset_password")
    db.commit()
    link = f"{get_settings().frontend_base_url}/reset-password?token={raw}"
    send_email(user.email, "Reset your PropTwin AI password", f"Use this link within one hour:\n{link}")


def confirm_password_reset(db: Session, raw: str, new_password: str) -> None:
    user = _consume_account_token(db, raw, "reset_password")
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
    audit.record(db, "user.password_reset", "user", user.id, actor_id=user.id)
    db.commit()


def request_email_verification(db: Session, user: User) -> str:
    raw = _issue_account_token(db, user, "verify_email")
    db.commit()
    link = f"{get_settings().frontend_base_url}/verify-email?token={raw}"
    return send_email(user.email, "Verify your PropTwin AI email", f"Confirm your email address:\n{link}")


def confirm_email_verification(db: Session, raw: str) -> None:
    user = _consume_account_token(db, raw, "verify_email")
    user.email_verified_at = utcnow()
    audit.record(db, "user.email_verified", "user", user.id, actor_id=user.id)
    db.commit()


def change_password(db: Session, user: User, current: str, new: str, session_id: uuid.UUID) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError(400, "invalid_password", "The current password is incorrect.")
    user.password_hash = hash_password(new)
    revoke_all_sessions(db, user.id, except_family=session_id)
    audit.record(db, "user.password_changed", "user", user.id, actor_id=user.id)
    db.commit()


def _wallet_message(address: str, nonce: str) -> str:
    return (
        "PropTwin AI wallet link\n"
        f"Address: {address}\n"
        f"Nonce: {nonce}\n"
        "Signing proves control of this wallet. It does not prove ownership of any property."
    )


def create_wallet_challenge(db: Session, user: User, address: str) -> str:
    nonce = secrets.token_hex(16)
    user.wallet_nonce = nonce
    db.commit()
    return _wallet_message(Web3.to_checksum_address(address), nonce)


def link_wallet(db: Session, user: User, address: str, signature: str) -> User:
    checksum = Web3.to_checksum_address(address)
    if not user.wallet_nonce:
        raise AppError(400, "no_wallet_challenge", "Request a wallet challenge first.")
    message = encode_defunct(text=_wallet_message(checksum, user.wallet_nonce))
    try:
        recovered = Account.recover_message(message, signature=signature)
    except Exception as exc:
        raise AppError(400, "invalid_signature", "The wallet signature is invalid.") from exc
    if recovered != checksum:
        raise AppError(400, "invalid_signature", "The wallet signature does not match this address.")
    other = db.scalar(select(User.id).where(User.wallet_address == checksum, User.id != user.id))
    if other:
        raise conflict("wallet_taken", "This wallet is linked to another account.")
    user.wallet_address = checksum
    user.wallet_nonce = None
    audit.record(db, "user.wallet_linked", "user", user.id, actor_id=user.id, address=checksum)
    db.commit()
    return user
