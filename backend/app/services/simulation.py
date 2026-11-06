"""Pure scenario arithmetic. No database, clock or randomness, so the same inputs always give the same result."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

HUNDRED = Decimal("100")
CENTS = Decimal("0.01")
PERCENT_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class ScenarioInputs:
    baseline_value: Decimal
    market_change_pct: Decimal = Decimal("0")
    renovation_value_uplift_pct: Decimal = Decimal("0")
    monthly_rent: Decimal | None = None
    monthly_rent_change_pct: Decimal = Decimal("0")
    annual_maintenance_cost: Decimal | None = None
    maintenance_change_pct: Decimal = Decimal("0")


@dataclass(frozen=True)
class ScenarioResult:
    scenario_value: Decimal
    absolute_difference: Decimal
    percentage_difference: Decimal
    annual_rental_income: Decimal | None
    rental_yield_pct: Decimal | None
    annual_maintenance_cost: Decimal | None


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _factor(pct: Decimal) -> Decimal:
    return 1 + pct / HUNDRED


def calculate(inputs: ScenarioInputs, adjusted_base: Decimal | None = None) -> ScenarioResult:
    """adjusted_base is the model's rerun value, if any. Differences are always measured from baseline_value."""
    base = inputs.baseline_value if adjusted_base is None else adjusted_base
    scenario = _money(base * _factor(inputs.market_change_pct) * _factor(inputs.renovation_value_uplift_pct))
    difference = scenario - inputs.baseline_value
    percentage = (difference / inputs.baseline_value * HUNDRED).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)

    annual_rent = rental_yield = None
    if inputs.monthly_rent is not None:
        annual_rent = _money(inputs.monthly_rent * _factor(inputs.monthly_rent_change_pct) * 12)
        if scenario > 0:
            rental_yield = (annual_rent / scenario * HUNDRED).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)

    maintenance = None
    if inputs.annual_maintenance_cost is not None:
        maintenance = _money(inputs.annual_maintenance_cost * _factor(inputs.maintenance_change_pct))

    return ScenarioResult(scenario, _money(difference), percentage, annual_rent, rental_yield, maintenance)
