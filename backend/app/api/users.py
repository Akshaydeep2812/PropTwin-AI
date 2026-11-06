from fastapi import APIRouter, Request

from app.api.dependencies import Auth, CurrentUser, DatabaseSession
from app.core.rate_limit import limiter
from app.schemas.auth import MessageResponse, PasswordChange, ProfileUpdate, UserRead, WalletChallengeRequest, WalletChallengeResponse, WalletLink
from app.services import audit, auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserRead)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DatabaseSession) -> UserRead:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("display_name") is not None:
        user.display_name = changes["display_name"].strip()
    if "phone" in changes:
        user.phone = changes["phone"] or None
    audit.record(db, "user.profile_updated", "user", user.id, actor_id=user.id, fields=sorted(changes))
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.post("/me/password", response_model=MessageResponse)
@limiter.limit("5/minute")
def change_password(request: Request, payload: PasswordChange, context: Auth, db: DatabaseSession) -> MessageResponse:
    auth_service.change_password(db, context.user, payload.current_password, payload.new_password, context.session_id)
    return MessageResponse(message="Password changed. Other sessions were signed out.")


@router.post("/me/wallet/challenge", response_model=WalletChallengeResponse)
def wallet_challenge(payload: WalletChallengeRequest, user: CurrentUser, db: DatabaseSession) -> WalletChallengeResponse:
    return WalletChallengeResponse(message=auth_service.create_wallet_challenge(db, user, payload.address))


@router.post("/me/wallet", response_model=UserRead)
def link_wallet(payload: WalletLink, user: CurrentUser, db: DatabaseSession) -> UserRead:
    return UserRead.model_validate(auth_service.link_wallet(db, user, payload.address, payload.signature))
