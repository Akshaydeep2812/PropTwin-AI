"""Fictional geography and market index for demo data. None of this describes a real place or market."""

import math
from dataclasses import dataclass
from datetime import date

DEMO_SOURCE = "PropTwin synthetic generator (fictional, not market data)"
INDEX_START = date(2016, 1, 1)


@dataclass(frozen=True)
class DemoLocality:
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    base_price_per_sqft: float
    annual_growth: float
    rent_yield: float


LOCALITIES = [
    DemoLocality("Harbor Crest", "Demo Metro", "Demo State North", 10.10, 70.10, 11800, 0.072, 0.027),
    DemoLocality("Lakeview Park", "Demo Metro", "Demo State North", 10.16, 70.21, 9400, 0.066, 0.029),
    DemoLocality("Old Market", "Demo Metro", "Demo State North", 10.04, 70.03, 7200, 0.041, 0.034),
    DemoLocality("Tech Meadows", "Demo Metro", "Demo State North", 10.27, 70.33, 8600, 0.094, 0.036),
    DemoLocality("Station Quarter", "Demo Metro", "Demo State North", 10.01, 70.18, 6300, 0.052, 0.038),
    DemoLocality("Green Terrace", "Sample City", "Demo State South", 11.42, 71.05, 5600, 0.058, 0.032),
    DemoLocality("Riverside", "Sample City", "Demo State South", 11.50, 71.12, 6900, 0.063, 0.030),
    DemoLocality("Fort Road", "Sample City", "Demo State South", 11.37, 70.98, 4300, 0.037, 0.041),
    DemoLocality("University Gate", "Sample City", "Demo State South", 11.55, 71.21, 5100, 0.071, 0.044),
    DemoLocality("Palm Vista", "Example Town", "Demo State South", 12.20, 72.01, 3400, 0.048, 0.039),
    DemoLocality("Mill Colony", "Example Town", "Demo State South", 12.26, 72.09, 2700, 0.031, 0.046),
    DemoLocality("Hilltop Enclave", "Example Town", "Demo State South", 12.33, 71.94, 4600, 0.067, 0.028),
]
LOCALITY_BY_NAME = {locality.name: locality for locality in LOCALITIES}


def market_index_for(locality: DemoLocality, when: date) -> float:
    """Exogenous index (100 at the start). It is defined independently of prices, so it cannot leak the target."""
    years = (when.year - INDEX_START.year) + (when.month - 1) / 12
    # Shared downturn and recovery, plus a locality-specific cycle, so the series is not a straight line.
    shock = 1 - 0.09 * math.exp(-(((years - 4.4) / 0.9) ** 2))
    cycle = 1 + 0.018 * math.sin(years * 1.7 + len(locality.name))
    return round(100 * (1 + locality.annual_growth) ** years * shock * cycle, 4)
