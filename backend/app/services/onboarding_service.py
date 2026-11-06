"""A role's getting-started checklist. Every step is ticked from real records, so it cannot claim progress that did not happen."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BlockchainRecord,
    DigitalTwin,
    MarketObservation,
    Property,
    PropertyVerificationRequest,
    SavedProperty,
    SimulationRun,
    User,
    Valuation,
    ValuationModelVersion,
)
from app.models.user import Role


def _step(key: str, title: str, description: str, done: bool, href: str, cta: str) -> dict:
    return {"key": key, "title": title, "description": description, "done": done, "href": href, "cta": cta}


def _first_missing(ids: list, present: set) -> object | None:
    """The oldest property still lacking this step, or the oldest property when all have it."""
    for item in ids:
        if item not in present:
            return item
    return ids[0] if ids else None


def _owner_steps(db: Session, user: User) -> list[dict]:
    ids = list(db.scalars(select(Property.id).where(Property.owner_id == user.id, Property.listing_status != "archived").order_by(Property.created_at, Property.id)))
    in_owned = lambda column: column.in_(ids)  # noqa: E731
    valued = set(db.scalars(select(Valuation.property_id).where(in_owned(Valuation.property_id)))) if ids else set()
    twins = set(db.scalars(select(DigitalTwin.property_id).where(in_owned(DigitalTwin.property_id)))) if ids else set()
    reviewed = set(db.scalars(select(PropertyVerificationRequest.property_id).where(in_owned(PropertyVerificationRequest.property_id)))) if ids else set()
    chained = set(db.scalars(select(BlockchainRecord.property_id).where(in_owned(BlockchainRecord.property_id), BlockchainRecord.record_version > 0))) if ids else set()
    simulated = db.scalar(select(SimulationRun.id).where(SimulationRun.created_by_id == user.id).limit(1)) is not None

    def link(template: str, present: set) -> str:
        target = _first_missing(ids, present)
        return "/properties/new" if target is None else template.format(id=target)

    return [
        _step("register", "Register a property", "Record its location, size and price. It stays private until you list it.", bool(ids), "/properties/new", "Register a property"),
        _step("estimate", "Get an AI estimate", "See a value, a range, and what moved the number.", bool(valued), link("/valuations?property={id}", valued), "Get an estimate"),
        _step("twin", "Create a digital twin", "A software copy that keeps every past state of the record.", bool(twins), link("/properties/{id}/twin", twins), "Create a twin"),
        _step("scenario", "Run a what-if scenario", "Test a market change or renovation without touching the real record.", simulated, link("/properties/{id}/twin", set()), "Run a scenario"),
        _step("verify", "Request verification", "Upload a document so that a named verifier can review it.", bool(reviewed), link("/properties/{id}#verification", reviewed), "Upload documents"),
        _step("chain", "Commit to the blockchain", "Store a salted hash, so that later changes to the record can be detected.", bool(chained), link("/properties/{id}/blockchain", chained), "Commit a record"),
    ]


def _investor_steps(db: Session, user: User) -> list[dict]:
    saved = list(db.scalars(select(SavedProperty.property_id).where(SavedProperty.user_id == user.id)))
    valued = db.scalar(select(Valuation.id).where(Valuation.requested_by_id == user.id).limit(1)) is not None
    simulated = db.scalar(select(SimulationRun.id).where(SimulationRun.created_by_id == user.id).limit(1)) is not None
    return [
        _step("save", "Save a listing", "Build a shortlist. Saved listings appear under Investments.", bool(saved), "/properties", "Browse listings"),
        _step("shortlist", "Shortlist two to compare", "Yield and price per square foot are easier to judge side by side.", len(saved) >= 2, "/properties", "Add another"),
        _step("estimate", "Check a price with an AI estimate", "See whether an asking price falls inside the estimate's range.", valued, f"/valuations?property={saved[0]}" if saved else "/valuations", "Get an estimate"),
        _step("scenario", "Run a what-if scenario", "Test a market fall or a rent rise on a listing that has a twin.", simulated, f"/simulator?property={saved[0]}" if saved else "/simulator", "Run a scenario"),
    ]


def _verifier_steps(db: Session, user: User) -> list[dict]:
    decided = db.scalar(select(PropertyVerificationRequest.id).where(PropertyVerificationRequest.reviewed_by_id == user.id).limit(1)) is not None
    return [_step("decide", "Record your first decision", "Open a request, read its documents, then approve or reject it with a note.", decided, "/verifier", "Open the queue")]


def _admin_steps(db: Session) -> list[dict]:
    active = db.scalar(select(ValuationModelVersion.id).where(ValuationModelVersion.status == "active").limit(1)) is not None
    market = db.scalar(select(MarketObservation.id).limit(1)) is not None
    verifiers = db.scalar(select(User.id).where(User.roles.any(Role.name == "verifier")).limit(1)) is not None
    return [
        _step("model", "Activate a valuation model", "Estimates stay unavailable until you approve and activate one.", active, "/admin", "Review models"),
        _step("market", "Load market data", "Market Insights and locality comparisons read from it.", market, "/help#admin", "See how"),
        _step("verifier", "Appoint a verifier", "Someone must hold this role before verification requests can be decided.", verifiers, "/admin", "Manage users"),
    ]


def build(db: Session, user: User) -> dict:
    if user.has_role("admin"):
        role, steps = "admin", _admin_steps(db)
    elif user.has_role("verifier"):
        role, steps = "verifier", _verifier_steps(db, user)
    elif user.has_role("owner"):
        role, steps = "owner", _owner_steps(db, user)
    else:
        role, steps = "investor", _investor_steps(db, user)
    return {"role": role, "steps": steps, "completed": sum(1 for step in steps if step["done"]), "total": len(steps)}
