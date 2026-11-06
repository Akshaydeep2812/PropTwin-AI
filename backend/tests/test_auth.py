from datetime import timedelta

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select

from app.core.security import hash_token
from app.models import AccountToken, AuditLog, RefreshToken, User
from app.models.types import utcnow
from app.services.auth_service import ROTATION_GRACE
from tests.conftest import PASSWORD

REGISTER = {"email": "Person@Example.com", "password": PASSWORD, "display_name": "Person"}


def test_register_normalizes_email_and_never_stores_plaintext(client, db):
    response = client.post("/api/v1/auth/register", json=REGISTER)
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "person@example.com"
    assert response.json()["user"]["roles"] == ["owner"]
    assert "password" not in response.text
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2") and PASSWORD not in user.password_hash


def test_duplicate_email_conflicts(client):
    assert client.post("/api/v1/auth/register", json=REGISTER).status_code == 201
    response = client.post("/api/v1/auth/register", json={**REGISTER, "email": "person@example.com"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize("role", ["admin", "verifier", "superuser"])
def test_cannot_self_assign_privileged_roles(client, role):
    assert client.post("/api/v1/auth/register", json={**REGISTER, "role": role}).status_code == 422


def test_register_rejects_extra_fields_and_short_password(client):
    assert client.post("/api/v1/auth/register", json={**REGISTER, "roles": ["admin"]}).status_code == 422
    assert client.post("/api/v1/auth/register", json={**REGISTER, "password": "short"}).status_code == 422


def test_login_failures_look_identical_and_are_audited(client, db):
    client.post("/api/v1/auth/register", json=REGISTER)
    wrong = client.post("/api/v1/auth/login", json={"email": REGISTER["email"], "password": "wrong-password-1"})
    missing = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["error"]["code"] == missing.json()["error"]["code"] == "invalid_credentials"
    assert len(db.scalars(select(AuditLog).where(AuditLog.action == "user.login_failed")).all()) == 2


def test_refresh_cookie_flags(client):
    cookie = client.post("/api/v1/auth/register", json=REGISTER).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1/auth" in cookie


def test_refresh_rotates_and_token_is_hashed_at_rest(client, db):
    client.post("/api/v1/auth/register", json=REGISTER)
    first = client.cookies.get("proptwin_refresh")
    assert db.scalar(select(RefreshToken)).token_hash == hash_token(first)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert client.cookies.get("proptwin_refresh") != first


def test_two_tabs_refreshing_together_both_keep_a_session(client):
    """Found while testing in a browser: a second tab's refresh looked like theft and would end the session."""
    client.post("/api/v1/auth/register", json=REGISTER)
    shared = client.cookies.get("proptwin_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    first_tab = client.cookies.get("proptwin_refresh")

    client.cookies.clear()
    client.cookies.set("proptwin_refresh", shared, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 200

    client.cookies.clear()
    client.cookies.set("proptwin_refresh", first_tab, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_refresh_reuse_after_the_grace_window_revokes_whole_family(client, db):
    client.post("/api/v1/auth/register", json=REGISTER)
    stolen = client.cookies.get("proptwin_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    current = client.cookies.get("proptwin_refresh")

    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(stolen)))
    token.rotated_at = utcnow() - ROTATION_GRACE - timedelta(seconds=1)
    db.commit()

    client.cookies.clear()
    client.cookies.set("proptwin_refresh", stolen, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401

    client.cookies.clear()
    client.cookies.set("proptwin_refresh", current, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_requires_csrf_header(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    response = client.post("/api/v1/auth/refresh", headers={"X-Requested-With": "other"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_required"


def test_logout_invalidates_access_token_immediately(client):
    token = client.post("/api/v1/auth/register", json=REGISTER).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_garbage_token_rejected_even_on_public_route(client):
    headers = {"Authorization": "Bearer not-a-token"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.get("/api/v1/properties/00000000-0000-0000-0000-000000000000", headers=headers).status_code == 401


def test_login_is_rate_limited(client):
    from app.core.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    try:
        credentials = {"email": "nobody@example.com", "password": "wrong-password-1"}
        codes = [client.post("/api/v1/auth/login", json=credentials).status_code for _ in range(11)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_password_reset_flow_is_single_use_and_revokes_sessions(client, db, monkeypatch):
    sent = {}
    monkeypatch.setattr("app.services.auth_service.send_email", lambda to, subject, body: sent.update(body=body) or "sent")
    old = client.post("/api/v1/auth/register", json=REGISTER).json()["access_token"]

    known = client.post("/api/v1/auth/password-reset/request", json={"email": REGISTER["email"]})
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]

    raw = sent["body"].split("token=")[1].strip()
    assert db.scalar(select(AccountToken)).token_hash == hash_token(raw)
    new_password = "another-long-password"
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": raw, "new_password": new_password}).status_code == 200
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": raw, "new_password": new_password}).status_code == 400
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": REGISTER["email"], "password": new_password}).status_code == 200


def test_email_verification_reports_unconfigured_delivery_honestly(make_actor):
    response = make_actor().post("/api/v1/auth/email-verification/request")
    assert response.status_code == 200
    assert response.json()["delivery"] == "not_configured"


def test_change_password_needs_current_and_keeps_this_session(make_actor):
    actor = make_actor()
    bad = actor.post("/api/v1/users/me/password", json={"current_password": "wrong", "new_password": "a-new-long-password"})
    assert bad.status_code == 400
    good = actor.post("/api/v1/users/me/password", json={"current_password": PASSWORD, "new_password": "a-new-long-password"})
    assert good.status_code == 200
    assert actor.get("/api/v1/auth/me").status_code == 200


def test_wallet_link_requires_a_valid_signature(make_actor):
    actor = make_actor()
    account, attacker = Account.create(), Account.create()
    message = actor.post("/api/v1/users/me/wallet/challenge", json={"address": account.address}).json()["message"]

    forged = attacker.sign_message(encode_defunct(text=message)).signature.to_0x_hex()
    assert actor.post("/api/v1/users/me/wallet", json={"address": account.address, "signature": forged}).status_code == 400

    signature = account.sign_message(encode_defunct(text=message)).signature.to_0x_hex()
    response = actor.post("/api/v1/users/me/wallet", json={"address": account.address, "signature": signature})
    assert response.status_code == 200 and response.json()["wallet_address"] == account.address
    # The nonce is single use, so a captured signature cannot be replayed.
    assert actor.post("/api/v1/users/me/wallet", json={"address": account.address, "signature": signature}).status_code == 400
