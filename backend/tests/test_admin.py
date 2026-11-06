from uuid import uuid4

from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import PASSWORD


def test_admin_routes_reject_everyone_else(make_actor, client):
    owner = make_actor()
    for path in ("/api/v1/admin/users", "/api/v1/admin/audit-logs", "/api/v1/admin/reports"):
        assert owner.get(path).status_code == 403
        client.cookies.clear()
        assert client.get(path).status_code == 401


def test_admin_grants_role_and_it_is_audited(make_actor, db):
    admin, user = make_actor("admin"), make_actor()
    response = admin.patch(f"/api/v1/admin/users/{user.user['id']}", json={"roles": ["verifier"]})
    assert response.status_code == 200 and response.json()["roles"] == ["verifier"]
    assert user.get("/api/v1/verification/queue").status_code == 200
    log = db.scalar(select(AuditLog).where(AuditLog.action == "admin.user_updated"))
    assert log.actor_id is not None and log.details["roles"] == ["verifier"]


def test_user_cannot_escalate_through_profile_or_admin_route(make_actor):
    user = make_actor()
    assert user.patch("/api/v1/users/me", json={"roles": ["admin"]}).status_code == 422
    assert user.patch(f"/api/v1/admin/users/{user.user['id']}", json={"roles": ["admin"]}).status_code == 403


def test_admin_cannot_change_own_account(make_actor):
    admin = make_actor("admin")
    response = admin.patch(f"/api/v1/admin/users/{admin.user['id']}", json={"roles": ["owner"]})
    assert response.status_code == 403 and response.json()["error"]["code"] == "cannot_modify_self"


def test_deactivation_ends_sessions_and_blocks_login(make_actor, client):
    admin, user = make_actor("admin"), make_actor()
    assert user.get("/api/v1/auth/me").status_code == 200
    admin.patch(f"/api/v1/admin/users/{user.user['id']}", json={"is_active": False})
    assert user.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": user.user["email"], "password": PASSWORD}).status_code == 401


def test_audit_log_filtering(make_actor):
    admin = make_actor("admin")
    make_actor()
    logs = admin.get("/api/v1/admin/audit-logs", params={"action": "user.registered"}).json()
    assert logs["total"] >= 1 and all(item["action"] == "user.registered" for item in logs["items"])


def test_notifications_are_private(make_actor):
    user = make_actor()
    assert user.post(f"/api/v1/notifications/{uuid4()}/read").status_code == 404
    assert user.get("/api/v1/notifications").json()["total"] == 0
