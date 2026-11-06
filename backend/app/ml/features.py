"""Feature definitions shared by offline training and online inference, so the two cannot drift apart.

Deliberately excluded:
- monthly rent: often derived from price or missing, and it is an output the twin reports.
- last sale price: reported as a comparison only; it is unavailable for many properties.
"""

from datetime import date
from typing import Any

SCHEMA_VERSION = 1

NUMERIC_FEATURES = [
    "built_up_area_sqft",
    "land_area_sqft",
    "bedrooms",
    "bathrooms",
    "property_age",
    "floor_number",
    "total_floors",
    "parking_spaces",
    "latitude",
    "longitude",
    "market_index",
    "amenity_count",
]
CATEGORICAL_FEATURES = ["property_type", "condition", "locality", "city"]
AMENITY_FLAGS = ["gym", "pool", "lift", "security", "garden", "clubhouse"]
BOOLEAN_FEATURES = [f"has_{name}" for name in AMENITY_FLAGS]
ALL_FEATURES = NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES

# Groups move together when measuring how sensitive a prediction is to one kind of input.
FACTOR_GROUPS = {
    "Built-up area": ["built_up_area_sqft"],
    "Land area": ["land_area_sqft"],
    "Rooms": ["bedrooms", "bathrooms"],
    "Age": ["property_age"],
    "Condition": ["condition"],
    "Property type": ["property_type"],
    "Location": ["locality", "city", "latitude", "longitude"],
    "Floor": ["floor_number", "total_floors"],
    "Parking": ["parking_spaces"],
    "Amenities": ["amenity_count", *BOOLEAN_FEATURES],
    "Market index": ["market_index"],
}


def build_feature_row(raw: dict[str, Any], as_of: date, market_index: float | None) -> dict[str, Any]:
    """Maps a property-like record to model inputs. Unknown values stay None for the imputer."""
    amenities = {str(item).strip().lower() for item in (raw.get("amenities") or [])}
    year = raw.get("construction_year")
    row: dict[str, Any] = {
        "built_up_area_sqft": _number(raw.get("built_up_area_sqft")),
        "land_area_sqft": _number(raw.get("land_area_sqft")),
        "bedrooms": _number(raw.get("bedrooms")),
        "bathrooms": _number(raw.get("bathrooms")),
        "property_age": None if year is None else max(0, as_of.year - int(year)),
        "floor_number": _number(raw.get("floor_number")),
        "total_floors": _number(raw.get("total_floors")),
        "parking_spaces": _number(raw.get("parking_spaces")),
        "latitude": _number(raw.get("latitude")),
        "longitude": _number(raw.get("longitude")),
        "market_index": market_index,
        "amenity_count": float(len(amenities)),
        "property_type": raw.get("property_type"),
        "condition": raw.get("condition"),
        "locality": raw.get("locality"),
        "city": raw.get("city"),
    }
    for name in AMENITY_FLAGS:
        row[f"has_{name}"] = float(name in amenities)
    return row


def _number(value: Any) -> float | None:
    return None if value is None else float(value)
