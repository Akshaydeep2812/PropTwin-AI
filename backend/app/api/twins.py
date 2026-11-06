from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DatabaseSession, Paging
from app.core.errors import forbidden
from app.schemas.common import Page
from app.schemas.twin import MarketPoint, SimulationRead, SimulationRequest, SnapshotRead, TwinRead, TwinUpdate
from app.services import access, twin_service

property_router = APIRouter(prefix="/properties", tags=["digital twins"])
router = APIRouter(prefix="/twins", tags=["digital twins"])


@property_router.post("/{property_id}/twin", response_model=TwinRead, status_code=status.HTTP_201_CREATED)
def create_twin(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return twin_service.serialize(twin_service.create_twin(db, access.get_managed(db, property_id, user), user))


@property_router.get("/{property_id}/twin", response_model=TwinRead)
def get_property_twin(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return twin_service.serialize(twin_service.get_by_property(db, property_id, user))


@router.patch("/{twin_id}", response_model=TwinRead)
def update_twin(twin_id: UUID, payload: TwinUpdate, user: CurrentUser, db: DatabaseSession) -> dict:
    twin, _ = twin_service.get_for_manager(db, twin_id, user)
    return twin_service.serialize(twin_service.update_operating(db, twin, user, payload.model_dump(exclude_unset=True)))


@router.post("/{twin_id}/simulate", response_model=SimulationRead, status_code=status.HTTP_201_CREATED)
def simulate(twin_id: UUID, payload: SimulationRequest, user: CurrentUser, db: DatabaseSession):
    twin, prop = twin_service.get_for_viewer(db, twin_id, user)
    # Verifiers can read a twin for review, but running scenarios is for the owner or an interested investor.
    if not (access.is_owner_or_admin(user, prop) or user.has_role("investor")):
        raise forbidden()
    return twin_service.simulate(db, twin, prop, user, payload.name, payload.model_dump(exclude={"name"}))


@router.get("/{twin_id}/history", response_model=Page[SnapshotRead])
def twin_history(twin_id: UUID, user: CurrentUser, db: DatabaseSession, paging: Paging) -> dict:
    twin, _ = twin_service.get_for_manager(db, twin_id, user)
    items, total = twin_service.history(db, twin, paging.page, paging.page_size)
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}


@router.get("/{twin_id}/simulations", response_model=Page[SimulationRead])
def twin_simulations(twin_id: UUID, user: CurrentUser, db: DatabaseSession, paging: Paging) -> dict:
    twin, prop = twin_service.get_for_viewer(db, twin_id, user)
    items, total = twin_service.simulations(db, twin, prop, user, paging.page, paging.page_size)
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}


@router.get("/{twin_id}/market", response_model=list[MarketPoint])
def twin_market(twin_id: UUID, user: CurrentUser, db: DatabaseSession) -> list[dict]:
    _, prop = twin_service.get_for_viewer(db, twin_id, user)
    return [
        {"period": row.period.isoformat(), "price_index": row.price_index, "is_synthetic": row.is_synthetic}
        for row in twin_service.market_series(db, prop.locality)
    ]
