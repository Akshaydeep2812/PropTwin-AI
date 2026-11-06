"""Read-side summaries of the locality market series. Every figure is derived from stored observations and carries their synthetic flag."""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import MarketObservation, Property
from app.services import access

PERCENT = Decimal("0.01")
HUNDRED = Decimal("100")


def _pct(value: Decimal) -> Decimal:
    return value.quantize(PERCENT, rounding=ROUND_HALF_UP)


def _years_back(period: date, years: int) -> date:
    return period.replace(year=period.year - years)


def gross_yield(monthly_rent_per_sqft: Decimal | None, price_per_sqft: Decimal | None) -> Decimal | None:
    if not monthly_rent_per_sqft or not price_per_sqft:
        return None
    return _pct(monthly_rent_per_sqft * 12 / price_per_sqft * HUNDRED)


def _summarize(series: list[MarketObservation], listings: int) -> dict:
    """Series is ordered oldest first. Growth compares the latest month with the same month in earlier years."""
    latest = series[-1]
    by_period = {row.period: row.price_index for row in series}
    change_12m = cagr_5y = None
    one_year = by_period.get(_years_back(latest.period, 1))
    if one_year:
        change_12m = _pct((latest.price_index / one_year - 1) * HUNDRED)
    five_years = by_period.get(_years_back(latest.period, 5))
    if five_years:
        cagr_5y = _pct((Decimal(float(latest.price_index / five_years) ** 0.2) - 1) * HUNDRED)
    return {
        "locality": latest.locality,
        "city": latest.city,
        "latest_period": latest.period,
        "price_index": latest.price_index,
        "price_per_sqft": latest.median_price_per_sqft,
        "monthly_rent_per_sqft": latest.median_monthly_rent_per_sqft,
        "gross_yield_pct": gross_yield(latest.median_monthly_rent_per_sqft, latest.median_price_per_sqft),
        "change_12m_pct": change_12m,
        "cagr_5y_pct": cagr_5y,
        "active_listings": listings,
        "is_synthetic": latest.is_synthetic,
        "source": latest.source,
    }


def _public_listing_counts(db: Session) -> dict[tuple[str, str], int]:
    rows = db.execute(
        select(Property.locality, Property.city, func.count())
        .where(Property.listing_status.in_(access.PUBLIC_STATUSES), Property.locality.is_not(None))
        .group_by(Property.locality, Property.city)
    )
    return {(locality, city): count for locality, city, count in rows}


def overview(db: Session) -> dict:
    rows = db.scalars(select(MarketObservation).where(MarketObservation.period <= date.today()).order_by(MarketObservation.period))
    grouped: dict[tuple[str, str], list[MarketObservation]] = defaultdict(list)
    for row in rows:
        grouped[(row.locality, row.city)].append(row)
    counts = _public_listing_counts(db)
    localities = [_summarize(series, counts.get(key, 0)) for key, series in grouped.items()]
    localities.sort(key=lambda item: (item["city"], item["locality"]))
    return {
        "localities": localities,
        "cities": sorted({item["city"] for item in localities}),
        "latest_period": max((item["latest_period"] for item in localities), default=None),
        "any_synthetic": any(item["is_synthetic"] for item in localities),
    }


def snapshot(db: Session, locality: str | None, city: str | None) -> dict | None:
    """One locality's summary, or None when no market series covers it."""
    if not locality:
        return None
    statement = select(MarketObservation).where(MarketObservation.locality == locality, MarketObservation.period <= date.today())
    if city:
        statement = statement.where(MarketObservation.city == city)
    series = list(db.scalars(statement.order_by(MarketObservation.period)))
    return _summarize(series, 0) if series else None


def trend(db: Session, locality: str) -> list[dict]:
    rows = list(db.scalars(select(MarketObservation).where(MarketObservation.locality == locality, MarketObservation.period <= date.today()).order_by(MarketObservation.period)))
    if not rows:
        raise not_found("Locality")
    return [{"period": row.period, "price_index": row.price_index, "price_per_sqft": row.median_price_per_sqft, "is_synthetic": row.is_synthetic} for row in rows]
