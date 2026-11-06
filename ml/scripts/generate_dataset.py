"""Generates the reproducible SYNTHETIC development dataset. Usage: python ml/scripts/generate_dataset.py

Every row is fictional. Metrics measured on this data show that the pipeline works, not that it can value real property.
A small share of rows is deliberately corrupted so that the cleaning stage is exercised on real faults.
"""

import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ml.demo_market import LOCALITIES, market_index_for  # noqa: E402
from app.ml.features import AMENITY_FLAGS  # noqa: E402

TYPE_MULTIPLIER = {"apartment": 1.0, "townhouse": 1.08, "house": 1.12, "villa": 1.32, "commercial": 1.2, "plot": 0.62}
TYPE_WEIGHTS = {"apartment": 0.55, "house": 0.17, "villa": 0.08, "townhouse": 0.08, "commercial": 0.07, "plot": 0.05}
CONDITION_MULTIPLIER = {"poor": 0.8, "fair": 0.91, "good": 1.0, "very_good": 1.08, "excellent": 1.17}
CONDITION_WEIGHTS = {"poor": 0.06, "fair": 0.2, "good": 0.42, "very_good": 0.22, "excellent": 0.1}
AMENITY_VALUE = {"gym": 0.012, "pool": 0.03, "lift": 0.022, "security": 0.015, "garden": 0.025, "clubhouse": 0.018}
START, END = date(2016, 1, 1), date(2026, 6, 30)


def _choose(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate_row(rng: random.Random) -> dict:
    locality = rng.choice(LOCALITIES)
    property_type = _choose(rng, TYPE_WEIGHTS)
    condition = _choose(rng, CONDITION_WEIGHTS)
    sold_on = START + timedelta(days=rng.randrange((END - START).days))
    built_year = rng.randint(1985, sold_on.year)
    age = sold_on.year - built_year

    is_plot = property_type == "plot"
    area_centre = {"apartment": 1150, "townhouse": 1700, "house": 2100, "villa": 3300, "commercial": 2600, "plot": 3000}[property_type]
    area = round(max(280.0, rng.lognormvariate(math.log(area_centre), 0.34)), 2)
    land = round(area * rng.uniform(1.3, 2.6), 2) if property_type in ("house", "villa", "townhouse") else (area if is_plot else None)
    bedrooms = None if is_plot or property_type == "commercial" else max(1, min(7, round(area / 520 + rng.gauss(0, 0.5))))
    bathrooms = None if is_plot else max(1, min(7, round((bedrooms or area / 800) * rng.uniform(0.7, 1.1))))
    stacked = property_type in ("apartment", "commercial")
    total_floors = rng.randint(4, 32) if stacked else (None if is_plot else rng.randint(1, 3))
    floor = rng.randint(0, total_floors) if stacked else None
    parking = 0 if is_plot else min(4, max(0, round(area / 1100 + rng.gauss(0, 0.45))))
    amenities = [] if is_plot else [name for name in AMENITY_FLAGS if rng.random() < (0.55 if stacked else 0.3)]

    index = market_index_for(locality, sold_on)
    value = locality.base_price_per_sqft * area ** 0.93 * 1000 ** 0.07
    value *= TYPE_MULTIPLIER[property_type] * CONDITION_MULTIPLIER[condition] * index / 100
    # Good upkeep offsets ageing, an interaction a purely additive model cannot represent.
    value *= (1 - min(0.38, 0.0095 * age)) if condition in ("poor", "fair") else (1 - min(0.22, 0.0048 * age))
    # Villas command a larger premium in expensive localities.
    if property_type == "villa":
        value *= 1 + (locality.base_price_per_sqft - 6000) / 30000
    if floor is not None:
        value *= 1 + 0.0035 * min(floor, 20) - (0.03 if floor == 0 else 0)
    value *= 1 + sum(AMENITY_VALUE[name] for name in amenities) + 0.018 * parking
    value *= rng.lognormvariate(0, 0.11)

    return {
        "transaction_date": sold_on.isoformat(),
        "property_type": property_type,
        "locality": locality.name,
        "city": locality.city,
        "state": locality.state,
        "latitude": round(locality.latitude + rng.gauss(0, 0.012), 6),
        "longitude": round(locality.longitude + rng.gauss(0, 0.012), 6),
        "built_up_area_sqft": area,
        "land_area_sqft": land,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "construction_year": built_year,
        "floor_number": floor,
        "total_floors": total_floors,
        "condition": condition,
        "parking_spaces": parking,
        "amenities": "|".join(amenities),
        "market_index": index,
        "sale_price": round(value, 2),
        "is_synthetic": True,
    }


def corrupt(rows: list[dict], rng: random.Random) -> list[dict]:
    """Injects the faults real exports contain: missing values, bad numbers, and duplicate rows."""
    for row in rows:
        roll = rng.random()
        if roll < 0.04:
            row["condition"] = None
        elif roll < 0.07:
            row["construction_year"] = None
        elif roll < 0.09:
            row["market_index"] = None
        elif roll < 0.095:
            row["sale_price"] = -abs(row["sale_price"])
        elif roll < 0.10:
            row["built_up_area_sqft"] = 0
        elif roll < 0.103:
            row["sale_price"] = 12.5
    return rows + [dict(row) for row in rng.sample(rows, k=len(rows) // 100)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=15000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "ml" / "data" / "synthetic_transactions.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows = corrupt([generate_row(rng) for _ in range(args.rows)], rng)
    rng.shuffle(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f"Wrote {len(rows)} synthetic rows to {args.output}")


if __name__ == "__main__":
    main()
