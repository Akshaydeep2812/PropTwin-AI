"""Turns stored records into the plain-language decision data shown on property pages and the owner's portfolio.

Nothing here predicts anything. Each figure is arithmetic on stored values, each sentence states one of those
comparisons, and none of them recommends buying or selling.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BlockchainRecord, DigitalTwin, Property, PropertyDocument, User, Valuation
from app.services import access, market_service, property_service, valuation_service

HUNDRED = Decimal("100")
PERCENT = Decimal("0.01")
PORTFOLIO_LIMIT = 200
# A gap this small between two per-sqft or yield figures is reported as "in line" rather than above or below.
IN_LINE_PCT = Decimal("3")
DISCLAIMER = "These comparisons are arithmetic on the figures shown. They are not financial advice, an appraisal, or a forecast."


def _pct(value: Decimal) -> Decimal:
    return value.quantize(PERCENT, rounding=ROUND_HALF_UP)


def _per_sqft(price: Decimal | None, area: Decimal | None) -> Decimal | None:
    return _pct(price / area) if price and area else None


def _gross_yield(monthly_rent: Decimal | None, price: Decimal | None) -> Decimal | None:
    return _pct(monthly_rent * 12 / price * HUNDRED) if monthly_rent and price else None


def _position(asking: Decimal | None, valuation: Valuation | None) -> str | None:
    if asking is None or valuation is None or valuation.interval_lower is None or valuation.interval_upper is None:
        return None
    if asking < valuation.interval_lower:
        return "below_range"
    if asking > valuation.interval_upper:
        return "above_range"
    return "within_range"


def _gap(asking: Decimal | None, valuation: Valuation | None) -> Decimal | None:
    return _pct((asking - valuation.predicted_value) / valuation.predicted_value * HUNDRED) if asking and valuation and valuation.predicted_value else None


def _is_current(prop: Property, valuation: Valuation | None) -> bool:
    return valuation is not None and valuation_service.inputs_unchanged(valuation, prop)


def _completeness(db: Session, prop: Property) -> dict:
    """Which optional details are still missing, because each one that is blank gives the model or the comparisons less to work with."""
    checks = [
        ("Built-up area", prop.built_up_area_sqft),
        ("Locality", prop.locality),
        ("Construction year", prop.construction_year),
        ("Condition", prop.condition),
        ("Asking price", prop.asking_price),
        ("Monthly rent", prop.monthly_rent),
        ("Amenities", prop.amenities),
        ("A photo", prop.images),
        ("A document", db.scalar(select(PropertyDocument.id).where(PropertyDocument.property_id == prop.id).limit(1))),
    ]
    if prop.property_type != "plot":
        checks.append(("Bathrooms", prop.bathrooms))
    if prop.property_type not in ("plot", "commercial"):
        checks.append(("Bedrooms", prop.bedrooms))
    if prop.property_type in ("apartment", "commercial"):
        checks.extend([("Floor number", prop.floor_number), ("Total floors", prop.total_floors)])
    missing = [label for label, value in checks if value is None or value == [] or value == ""]
    return {"percent": round((len(checks) - len(missing)) * 100 / len(checks)), "missing": missing}


def _takeaways(position, gap, premium, gross, market_yield, change_12m, valuation, is_current, verification, on_chain) -> list[dict]:
    notes: list[dict] = []

    def add(tone: str, text: str) -> None:
        notes.append({"tone": tone, "text": text})

    if valuation is None:
        add("neutral", "No AI estimate exists yet, so the asking price has nothing to be checked against.")
    else:
        if position == "above_range":
            add("caution", f"The asking price is {abs(gap)}% above the AI estimate and outside its range.")
        elif position == "below_range":
            add("positive", f"The asking price is {abs(gap)}% below the AI estimate and outside its range. Check why before relying on it.")
        elif position == "within_range":
            add("neutral", f"The asking price is inside the AI estimate's range, {abs(gap)}% {'above' if gap > 0 else 'below'} its central figure.")
        if not is_current:
            add("caution", "The details the latest estimate used have since changed, so that estimate is out of date.")

    if premium is not None:
        if abs(premium) < IN_LINE_PCT:
            add("neutral", "The asking price per square foot is in line with the locality median.")
        else:
            add("caution" if premium > 0 else "positive", f"The asking price per square foot is {abs(premium)}% {'above' if premium > 0 else 'below'} the locality median.")

    if gross is not None and market_yield is not None:
        difference = gross - market_yield
        if abs(difference) < Decimal("0.2"):
            add("neutral", f"The gross rental yield of {gross}% is in line with the locality's {market_yield}%.")
        else:
            add("positive" if difference > 0 else "caution", f"The gross rental yield of {gross}% is {'above' if difference > 0 else 'below'} the locality's {market_yield}%.")

    if change_12m is not None:
        add("neutral", f"The locality's price index moved {'+' if change_12m > 0 else ''}{change_12m}% over the last 12 months. Past movement does not predict future prices.")

    if verification == "verified":
        add("positive", "A verifier reviewed the submitted documents and approved them. This is not a legal title search.")
    elif verification == "rejected":
        add("caution", "A verifier reviewed the submitted documents and rejected them.")
    else:
        add("caution", "No verifier has approved this property's documents yet.")

    if on_chain:
        add("positive", "A hash of this record is on the blockchain, so later changes to it can be detected. This does not prove ownership.")
    return notes


def build(db: Session, prop: Property, viewer: User | None) -> dict:
    valuation = db.scalar(select(Valuation).where(Valuation.property_id == prop.id).order_by(Valuation.created_at.desc()).limit(1))
    market = market_service.snapshot(db, prop.locality, prop.city)
    # Market series are stored in the default currency, so they cannot be compared with a listing priced in another.
    comparable = market if market and prop.currency == get_settings().default_currency else None
    record = db.scalar(select(BlockchainRecord).where(BlockchainRecord.property_id == prop.id))
    has_twin = db.scalar(select(DigitalTwin.id).where(DigitalTwin.property_id == prop.id)) is not None

    asking_per_sqft = _per_sqft(prop.asking_price, prop.built_up_area_sqft)
    market_per_sqft = comparable["price_per_sqft"] if comparable else None
    premium = _pct((asking_per_sqft / market_per_sqft - 1) * HUNDRED) if asking_per_sqft and market_per_sqft else None
    gross = _gross_yield(prop.monthly_rent, prop.asking_price)
    market_yield = comparable["gross_yield_pct"] if comparable else None
    position, gap = _position(prop.asking_price, valuation), _gap(prop.asking_price, valuation)
    is_current = _is_current(prop, valuation)
    on_chain = record is not None and record.record_version > 0
    change_12m = market["change_12m_pct"] if market else None

    return {
        "property_id": prop.id,
        "currency": prop.currency,
        "asking_price": prop.asking_price,
        "asking_per_sqft": asking_per_sqft,
        "market_per_sqft": market_per_sqft,
        "premium_to_market_pct": premium,
        "gross_yield_pct": gross,
        "market_yield_pct": market_yield,
        "market": None if market is None else {
            "locality": market["locality"],
            "latest_period": market["latest_period"],
            "change_12m_pct": change_12m,
            "cagr_5y_pct": market["cagr_5y_pct"],
            "is_synthetic": market["is_synthetic"],
        },
        "estimate": None if valuation is None else {
            "value": valuation.predicted_value,
            "lower": valuation.interval_lower,
            "upper": valuation.interval_upper,
            "predicted_at": valuation.created_at,
            "model_version": valuation.model_version.version,
            "trained_on_synthetic_data": valuation.model_version.trained_on_synthetic_data,
            "is_current": is_current,
        },
        "price_position": position,
        "asking_vs_estimate_pct": gap,
        "status": {"has_estimate": valuation is not None, "estimate_current": is_current, "has_twin": has_twin, "verification_status": prop.verification_status, "on_chain": on_chain},
        "takeaways": _takeaways(position, gap, premium, gross, market_yield, change_12m, valuation, is_current, prop.verification_status, on_chain),
        "completeness": _completeness(db, prop) if access.is_owner_or_admin(viewer, prop) else None,
        "disclaimer": DISCLAIMER,
    }


def _next_action(prop: Property, valuation: Valuation | None, is_current: bool, has_twin: bool, on_chain: bool) -> dict | None:
    """The single most useful step for this property, in the order the later steps depend on the earlier ones."""
    base = f"/properties/{prop.id}"
    if prop.built_up_area_sqft is None:
        return {"label": "Add built-up area", "href": f"{base}/edit", "reason": "The model needs it to make an estimate."}
    if valuation is None:
        return {"label": "Get an AI estimate", "href": f"/valuations?property={prop.id}", "reason": "No estimate yet."}
    if not is_current:
        return {"label": "Refresh the estimate", "href": f"/valuations?property={prop.id}", "reason": "Its details changed after the last estimate."}
    if not has_twin:
        return {"label": "Create a digital twin", "href": f"{base}/twin", "reason": "Scenarios need a twin."}
    if prop.verification_status in ("unverified", "rejected"):
        return {"label": "Request verification", "href": f"{base}#verification", "reason": "Documents have not been approved."}
    if not on_chain:
        return {"label": "Commit to the blockchain", "href": f"{base}/blockchain", "reason": "No tamper-evident record yet."}
    return None


def portfolio(db: Session, user: User) -> dict:
    properties, total = property_service.list_owned(db, user, 1, PORTFOLIO_LIMIT)
    ids: list[uuid.UUID] = [prop.id for prop in properties]
    latest: dict[uuid.UUID, Valuation] = {}
    twins: set[uuid.UUID] = set()
    chained: set[uuid.UUID] = set()
    if ids:
        for valuation in db.scalars(select(Valuation).where(Valuation.property_id.in_(ids)).order_by(Valuation.created_at.desc())):
            latest.setdefault(valuation.property_id, valuation)
        twins = set(db.scalars(select(DigitalTwin.property_id).where(DigitalTwin.property_id.in_(ids))))
        chained = set(db.scalars(select(BlockchainRecord.property_id).where(BlockchainRecord.property_id.in_(ids), BlockchainRecord.record_version > 0)))

    rows = []
    for prop in properties:
        valuation = latest.get(prop.id)
        is_current = _is_current(prop, valuation)
        rows.append(
            {
                "id": prop.id,
                "title": prop.title,
                "locality": prop.locality,
                "city": prop.city,
                "property_type": prop.property_type,
                "currency": prop.currency,
                "listing_status": prop.listing_status,
                "verification_status": prop.verification_status,
                "asking_price": prop.asking_price,
                "monthly_rent": prop.monthly_rent,
                "estimate": None if valuation is None else valuation.predicted_value,
                "estimate_current": is_current,
                "asking_vs_estimate_pct": _gap(prop.asking_price, valuation),
                "price_position": _position(prop.asking_price, valuation),
                "gross_yield_pct": _gross_yield(prop.monthly_rent, prop.asking_price),
                "has_twin": prop.id in twins,
                "on_chain": prop.id in chained,
                "is_demo": prop.is_demo,
                "next_action": _next_action(prop, valuation, is_current, prop.id in twins, prop.id in chained),
            }
        )

    # Sums across currencies would be meaningless, so totals are given only for a single-currency portfolio.
    currencies = {row["currency"] for row in rows}
    single = len(currencies) == 1
    return {
        "items": rows,
        "total_properties": total,
        "truncated": total > len(rows),
        "currency": next(iter(currencies)) if single else None,
        "total_estimate": sum((row["estimate"] for row in rows if row["estimate"] is not None), Decimal("0")) if single else None,
        "total_annual_rent": sum((row["monthly_rent"] * 12 for row in rows if row["monthly_rent"] is not None), Decimal("0")) if single else None,
        "estimated_count": sum(1 for row in rows if row["estimate"] is not None),
        "verified_count": sum(1 for row in rows if row["verification_status"] == "verified"),
        "twin_count": sum(1 for row in rows if row["has_twin"]),
        "on_chain_count": sum(1 for row in rows if row["on_chain"]),
        "action_count": sum(1 for row in rows if row["next_action"] is not None),
    }
