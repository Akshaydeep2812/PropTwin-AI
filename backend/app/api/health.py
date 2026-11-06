from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.services import blockchain_service, valuation_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    """Only the database decides readiness. The app still serves its other features without a model or chain."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppError(503, "database_unavailable", "Database is unavailable.") from exc
    chain = blockchain_service.network_status()
    return {
        "status": "ready",
        "database": "ok",
        "model_available": valuation_service.model_status(db)["available"],
        "blockchain_reachable": chain["reachable"],
    }
