"""Deterministic record hashing. Pure functions: the same record and salt always give the same hash.

Version 1 covers the factual attributes of a property. It deliberately leaves out:
- title and description, which are marketing text;
- listing and verification status, which change as workflow state;
- the owner, which changes through a transfer and is tracked by the contract's controller;
- asking price and rent, which are offers rather than facts about the property.

Changing the covered fields or the normalization requires a new HASH_VERSION, so old commitments stay checkable.
"""

import json
import secrets
import unicodedata
from decimal import Decimal
from typing import Any

from web3 import Web3

HASH_VERSION = 1
COVERED_FIELDS = (
    "property_id", "property_type", "address_line1", "locality", "city", "state", "postal_code", "latitude", "longitude",
    "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year", "floor_number", "total_floors",
    "condition", "amenities", "parking_spaces", "last_sale_price", "last_sale_date",
)


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def _normalize_decimal(value: Decimal) -> str:
    """1200, 1200.0 and 1200.00 must hash identically, whatever scale the database returned."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return _normalize_decimal(value)
    if isinstance(value, float):
        raise TypeError("Floats are not hashable here: their text form is not stable. Use Decimal.")
    if isinstance(value, (list, tuple, set)):
        return sorted(_normalize_text(str(item)).lower() for item in value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _normalize_text(str(value))


def build_payload(prop: Any) -> dict[str, Any]:
    payload = {"hash_version": HASH_VERSION, "property_id": str(prop.id)}
    for field in COVERED_FIELDS:
        if field != "property_id":
            payload[field] = normalize_value(getattr(prop, field))
    return payload


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(payload: dict[str, Any], salt: str) -> str:
    """The salt stops anyone hashing guessed addresses and comparing against the public on-chain value."""
    return Web3.keccak(Web3.to_bytes(hexstr=salt) + canonical_json(payload)).to_0x_hex()


def new_salt() -> str:
    return "0x" + secrets.token_hex(32)


def property_key(property_id: Any) -> str:
    return Web3.keccak(text=f"proptwin:property:{property_id}").to_0x_hex()


def valuation_commitment(valuation_id: Any, value: Decimal, model_version: str, salt: str) -> str:
    payload = {"hash_version": HASH_VERSION, "valuation_id": str(valuation_id), "predicted_value": _normalize_decimal(value), "model_version": model_version}
    return record_hash(payload, salt)


def changed_fields(committed: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if committed is None:
        return []
    return sorted(key for key in current if committed.get(key) != current[key])
