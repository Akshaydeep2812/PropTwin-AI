from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.dependencies import AdminUser, DatabaseSession, Paging
from app.core.errors import AppError, not_found
from app.models import AuditLog, BlockchainTransaction, PropertyReport, User
from app.schemas.admin import AdminUserUpdate, AuditLogRead
from app.schemas.auth import UserRead
from app.schemas.blockchain import TransactionRead
from app.schemas.common import Page
from app.schemas.dashboard import MonitoringRead
from app.schemas.property import ReportRead, ReportResolve
from app.services import access, audit, auth_service, dashboard_service
from app.services.property_service import escape_like

router = APIRouter(prefix="/admin", tags=["administration"])


def _page(db, model, conditions, order, paging) -> dict:
    total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    items = db.scalars(select(model).where(*conditions).order_by(order).offset((paging.page - 1) * paging.page_size).limit(paging.page_size)).all()
    return {"items": list(items), "page": paging.page, "page_size": paging.page_size, "total": total}


@router.get("/users", response_model=Page[UserRead])
def list_users(admin: AdminUser, db: DatabaseSession, paging: Paging, q: str | None = Query(default=None, max_length=100)) -> dict:
    conditions = []
    if q:
        pattern = f"%{escape_like(q)}%"
        conditions.append(or_(User.email.ilike(pattern, escape="\\"), User.display_name.ilike(pattern, escape="\\")))
    return _page(db, User, conditions, User.created_at.desc(), paging)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: UUID, payload: AdminUserUpdate, admin: AdminUser, db: DatabaseSession) -> UserRead:
    if user_id == admin.id:
        raise AppError(403, "cannot_modify_self", "Administrators cannot change their own roles or status.")
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    changes = payload.model_dump(exclude_none=True)
    if "is_active" in changes:
        user.is_active = changes["is_active"]
        if not user.is_active:
            auth_service.revoke_all_sessions(db, user.id)
    if "roles" in changes:
        user.roles = [auth_service.get_role(db, name) for name in sorted(set(changes["roles"]))]
    audit.record(db, "admin.user_updated", "user", user.id, actor_id=admin.id, **changes)
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/audit-logs", response_model=Page[AuditLogRead])
def audit_logs(
    admin: AdminUser,
    db: DatabaseSession,
    paging: Paging,
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=50),
    entity_id: str | None = Query(default=None, max_length=64),
) -> dict:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    return _page(db, AuditLog, conditions, AuditLog.created_at.desc(), paging)


@router.get("/transactions", response_model=Page[TransactionRead])
def list_transactions(admin: AdminUser, db: DatabaseSession, paging: Paging, status: str | None = Query(default=None, max_length=20)) -> dict:
    conditions = [] if status is None else [BlockchainTransaction.status == status]
    return _page(db, BlockchainTransaction, conditions, BlockchainTransaction.created_at.desc(), paging)


@router.get("/monitoring", response_model=MonitoringRead)
def monitoring(admin: AdminUser, db: DatabaseSession) -> dict:
    return dashboard_service.monitoring(db)


@router.get("/reports", response_model=Page[ReportRead])
def list_reports(admin: AdminUser, db: DatabaseSession, paging: Paging, status: str = "open") -> dict:
    return _page(db, PropertyReport, [PropertyReport.status == status], PropertyReport.created_at, paging)


@router.patch("/reports/{report_id}", response_model=ReportRead)
def resolve_report(report_id: UUID, payload: ReportResolve, admin: AdminUser, db: DatabaseSession) -> PropertyReport:
    report = db.get(PropertyReport, report_id)
    if report is None:
        raise not_found("Report")
    report.status = payload.status
    report.resolved_by_id = admin.id
    if payload.archive_listing:
        access.load_property(db, report.property_id).listing_status = "archived"
    audit.record(db, "admin.report_resolved", "property_report", report.id, actor_id=admin.id, status=payload.status, archived=payload.archive_listing)
    db.commit()
    db.refresh(report)
    return report
