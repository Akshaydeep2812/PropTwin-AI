from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DatabaseSession
from app.schemas.dashboard import DashboardRead
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
def dashboard(user: CurrentUser, db: DatabaseSession) -> dict:
    return dashboard_service.build(db, user)
