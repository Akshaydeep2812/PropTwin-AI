"""Loads clearly labelled demo data. Usage (from the repo root): python database/seed/seed_demo.py

Everything created here is fictional and flagged is_demo or is_synthetic. Safe to run repeatedly.
Refuses to run when APP_ENV=production. Passwords come from DEMO_PASSWORD, or are generated and printed once.
"""

import os
import random
import secrets
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.ml.demo_market import DEMO_SOURCE, INDEX_START, LOCALITIES, market_index_for  # noqa: E402
from app.ml.features import AMENITY_FLAGS  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models import DigitalTwin, MarketObservation, Property, PropertyOwnershipHistory, PropertyVerificationRequest, SimulationRun, User, Valuation  # noqa: E402
from app.models.types import utcnow  # noqa: E402
from app.services import auth_service, property_service, twin_service, valuation_service  # noqa: E402

DEMO_USERS = [
    ("demo.owner@proptwin.example", "Demo Owner", ["owner"]),
    ("demo.investor@proptwin.example", "Demo Investor", ["investor"]),
    ("demo.verifier@proptwin.example", "Demo Verifier", ["verifier"]),
    ("demo.admin@proptwin.example", "Demo Admin", ["admin", "owner"]),
]
AREA_BY_TYPE = {"apartment": (650, 2000), "house": (1400, 3200), "villa": (2600, 5200), "townhouse": (1300, 2400), "commercial": (1500, 4000)}
CONDITIONS = ["fair", "good", "good", "very_good", "excellent"]
PROPERTY_COUNT = 24


def seed_users(db) -> tuple[dict[str, User], str | None]:
    password = os.environ.get("DEMO_PASSWORD")
    generated = None
    if not password:
        password = generated = secrets.token_urlsafe(14)
    users = {}
    created_any = False
    for email, name, roles in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = auth_service.register_user(db, email, password, name, roles[0])
            user.is_demo = True
            user.email_verified_at = utcnow()
            for role in roles[1:]:
                user.roles.append(auth_service.get_role(db, role))
            created_any = True
        users[email] = user
    return users, generated if created_any else None


def seed_market(db) -> int:
    existing = db.scalar(select(func.count()).select_from(MarketObservation).where(MarketObservation.source == DEMO_SOURCE)) or 0
    if existing:
        return 0
    today = date.today()
    count = 0
    for locality in LOCALITIES:
        period = INDEX_START
        while period <= today:
            index = market_index_for(locality, period)
            db.add(
                MarketObservation(
                    locality=locality.name,
                    city=locality.city,
                    period=period,
                    price_index=Decimal(str(index)),
                    median_price_per_sqft=Decimal(str(round(locality.base_price_per_sqft * index / 100, 2))),
                    median_monthly_rent_per_sqft=Decimal(str(round(locality.base_price_per_sqft * index / 100 * locality.rent_yield / 12, 4))),
                    source=DEMO_SOURCE,
                    is_synthetic=True,
                )
            )
            count += 1
            period = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    return count


def seed_properties(db, owner: User) -> int:
    existing = db.scalar(select(func.count()).select_from(Property).where(Property.is_demo.is_(True))) or 0
    if existing:
        return 0
    rng = random.Random(7)
    types = list(AREA_BY_TYPE)
    for number in range(1, PROPERTY_COUNT + 1):
        locality = LOCALITIES[(number - 1) % len(LOCALITIES)]
        property_type = types[(number - 1) % len(types)] if number % 3 == 0 else "apartment"
        area = Decimal(rng.randint(*AREA_BY_TYPE[property_type]))
        index = market_index_for(locality, date.today()) / 100
        built = rng.randint(1996, 2024)
        stacked = property_type in ("apartment", "commercial")
        total_floors = rng.randint(6, 28) if stacked else rng.randint(1, 3)
        bedrooms = None if property_type == "commercial" else max(1, min(6, round(float(area) / 520)))
        reference = float(area) * locality.base_price_per_sqft * index
        prop = Property(
            owner_id=owner.id,
            title=f"[DEMO] {property_type.title()} in {locality.name} #{number}",
            description="Fictional listing created by the seed script. It does not describe a real property.",
            property_type=property_type,
            address_line1=f"{number} Example Road",
            locality=locality.name,
            city=locality.city,
            state=locality.state,
            postal_code=f"{100000 + number}",
            latitude=Decimal(str(round(locality.latitude + rng.uniform(-0.01, 0.01), 6))),
            longitude=Decimal(str(round(locality.longitude + rng.uniform(-0.01, 0.01), 6))),
            built_up_area_sqft=area,
            land_area_sqft=area * Decimal("1.8") if property_type in ("house", "villa", "townhouse") else None,
            bedrooms=bedrooms,
            bathrooms=max(1, (bedrooms or 2) - rng.randint(0, 1)),
            construction_year=built,
            floor_number=rng.randint(0, total_floors) if stacked else None,
            total_floors=total_floors,
            condition=rng.choice(CONDITIONS),
            amenities=sorted(rng.sample(AMENITY_FLAGS, k=rng.randint(1, 4))),
            parking_spaces=rng.randint(0, 2),
            last_sale_price=Decimal(str(round(reference * rng.uniform(0.6, 0.85), -3))),
            last_sale_date=date(rng.randint(2017, 2023), rng.randint(1, 12), 15),
            asking_price=Decimal(str(round(reference * rng.uniform(0.95, 1.15), -4))),
            monthly_rent=Decimal(str(round(reference * locality.rent_yield / 12, -2))),
            listing_status="listed" if number % 5 else "draft",
            is_demo=True,
        )
        db.add(prop)
        db.flush()
        db.add(PropertyOwnershipHistory(property_id=prop.id, owner_id=owner.id, source="demo_seed", effective_from=utcnow()))
    return PROPERTY_COUNT


# A minimal, valid PDF. Its text says what it is, so that a verifier opening it is never misled.
DEMO_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 300]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 60>>stream\nBT /F1 18 Tf 40 200 Td (Fictional demo document. Not a deed.) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)
DEMO_SCENARIOS = [
    {"name": "Market down 10%", "market_change_pct": Decimal("-10")},
    {"name": "Renovation adds 8%", "renovation_value_uplift_pct": Decimal("8")},
    {"name": "Rent up 10%", "monthly_rent_change_pct": Decimal("10")},
]
SCENARIO_DEFAULTS = {"market_change_pct": Decimal("0"), "renovation_value_uplift_pct": Decimal("0"), "monthly_rent_change_pct": Decimal("0"), "maintenance_change_pct": Decimal("0")}


def seed_activity(db, users: dict[str, User]) -> str:
    """Real estimates, twins and scenarios on the demo records, so that a first-time visitor sees a working product.

    Everything goes through the same services as the app. Nothing is back-dated, and only the active model produces
    estimates. Each step skips what already exists, so this is safe to run again.
    """
    if not valuation_service.model_status(db)["available"]:
        return "Skipped demo activity: no model is active yet. Run this script again after activating one."
    owner = users["demo.owner@proptwin.example"]
    investor = users["demo.investor@proptwin.example"]
    verifier = users["demo.verifier@proptwin.example"]
    demo = list(db.scalars(select(Property).where(Property.is_demo.is_(True), Property.owner_id == owner.id).order_by(Property.title)))
    listed = [prop for prop in demo if prop.listing_status == "listed"]

    valued = 0
    for prop in demo:
        if db.scalar(select(Valuation.id).where(Valuation.property_id == prop.id).limit(1)):
            continue
        try:
            valuation_service.value_property(db, prop, owner)
            db.commit()
            valued += 1
        except AppError as exc:
            db.rollback()
            print(f"  No estimate for {prop.title}: {exc.message}")

    scenarios = 0
    for prop in listed[:6]:
        twin = db.scalar(select(DigitalTwin).where(DigitalTwin.property_id == prop.id))
        if twin is None:
            twin = twin_service.create_twin(db, prop, owner)
        if twin.current_estimated_value is None or db.scalar(select(SimulationRun.id).where(SimulationRun.twin_id == twin.id).limit(1)):
            continue
        for scenario in DEMO_SCENARIOS:
            payload = {**SCENARIO_DEFAULTS, **scenario}
            twin_service.simulate(db, twin, prop, owner, payload.pop("name"), payload)
            scenarios += 1
        db.commit()

    for prop in listed[:4]:
        property_service.save_favorite(db, investor, prop)

    # Two requests approved and two waiting, so that the owner sees an outcome and the verifier has work to do.
    if not db.scalar(select(PropertyVerificationRequest.id).where(PropertyVerificationRequest.property_id.in_([prop.id for prop in demo])).limit(1)):
        for position, prop in enumerate(listed[:4]):
            property_service.add_document(db, prop, owner, DEMO_PDF, f"demo-document-{position + 1}.pdf", "other")
            request = property_service.submit_verification(db, prop, owner, "Fictional demo request.")
            if position < 2:
                property_service.decide_verification(db, request.id, verifier, "approved", "Demo decision on a fictional record.")
    return f"Demo activity ready: {valued} new estimates, {scenarios} new scenarios, 4 saved listings."


def main() -> int:
    if get_settings().is_production:
        print("Refusing to load demo data in production.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        users, generated = seed_users(db)
        observations = seed_market(db)
        properties = seed_properties(db, users["demo.owner@proptwin.example"])
        db.commit()
        activity = seed_activity(db, users)
    print(activity)
    print(f"Demo data ready: {len(users)} users, {properties} new properties, {observations} new market observations.")
    print("All of it is fictional and flagged as demo data.")
    for email, _, roles in DEMO_USERS:
        print(f"  {email}  ({', '.join(roles)})")
    if generated:
        print(f"Generated password for the new demo accounts (shown once): {generated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
