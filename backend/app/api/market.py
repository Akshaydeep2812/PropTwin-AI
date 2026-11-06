from fastapi import APIRouter

from app.api.dependencies import DatabaseSession
from app.schemas.insights import MarketOverview, MarketTrendPoint
from app.services import market_service

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/localities", response_model=MarketOverview)
def localities(db: DatabaseSession) -> dict:
    return market_service.overview(db)


@router.get("/localities/{locality}/trend", response_model=list[MarketTrendPoint])
def locality_trend(locality: str, db: DatabaseSession) -> list[dict]:
    return market_service.trend(db, locality)
