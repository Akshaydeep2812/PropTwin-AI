from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.blockchain import hashing

SALT = "0x" + "ab" * 32


def _prop(**overrides):
    values = {
        "id": "2f1c7e0a-0000-4000-8000-000000000001", "property_type": "apartment", "address_line1": "12 Private Street", "locality": "Riverside", "city": "Demo City",
        "state": "Demo State", "postal_code": "500001", "latitude": None, "longitude": None, "built_up_area_sqft": Decimal("1200.00"), "land_area_sqft": None,
        "bedrooms": 2, "bathrooms": 2, "construction_year": 2015, "floor_number": 3, "total_floors": 10, "condition": "good", "amenities": ["gym", "lift"],
        "parking_spaces": 1, "last_sale_price": Decimal("6000000.00"), "last_sale_date": date(2020, 1, 15), "title": "Title", "description": "Text", "asking_price": Decimal("1"),
    }
    return SimpleNamespace(**{**values, **overrides})


def _hash(prop) -> str:
    return hashing.record_hash(hashing.build_payload(prop), SALT)


def test_hash_is_deterministic_and_well_formed():
    first, second = _hash(_prop()), _hash(_prop())
    assert first == second and first.startswith("0x") and len(first) == 66


def test_known_answer_pins_the_algorithm():
    """If this changes, every stored commitment becomes uncheckable. Introduce a new HASH_VERSION instead."""
    payload = {"hash_version": 1, "b": "x", "a": None}
    assert hashing.canonical_json(payload) == b'{"a":null,"b":"x","hash_version":1}'
    assert hashing.record_hash(payload, SALT) == "0x" + _expected_digest()


def _expected_digest() -> str:
    from Crypto.Hash import keccak

    digest = keccak.new(digest_bits=256)
    digest.update(bytes.fromhex("ab" * 32) + b'{"a":null,"b":"x","hash_version":1}')
    return digest.hexdigest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("property_type", "villa"), ("address_line1", "13 Private Street"), ("locality", "Fort Road"), ("city", "Other"), ("state", "Other"), ("postal_code", "500002"),
        ("latitude", Decimal("1.5")), ("longitude", Decimal("1.5")), ("built_up_area_sqft", Decimal("1200.01")), ("land_area_sqft", Decimal("5")), ("bedrooms", 3), ("bathrooms", 3),
        ("construction_year", 2016), ("floor_number", 4), ("total_floors", 11), ("condition", "fair"), ("amenities", ["gym"]), ("parking_spaces", 2),
        ("last_sale_price", Decimal("6000000.01")), ("last_sale_date", date(2020, 1, 16)), ("id", "2f1c7e0a-0000-4000-8000-000000000002"),
    ],
)
def test_changing_any_covered_field_changes_the_hash(field, value):
    assert _hash(_prop(**{field: value})) != _hash(_prop())


@pytest.mark.parametrize("field,value", [("title", "New"), ("description", "New"), ("asking_price", Decimal("2"))])
def test_uncovered_fields_do_not_change_the_hash(field, value):
    assert _hash(_prop(**{field: value})) == _hash(_prop())


def test_covered_field_list_matches_the_payload():
    payload = hashing.build_payload(_prop())
    assert set(payload) == set(hashing.COVERED_FIELDS) | {"hash_version"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"built_up_area_sqft": Decimal("1200")},
        {"built_up_area_sqft": Decimal("1200.0000")},
        {"amenities": ["lift", "gym"]},
        {"amenities": ["LIFT", " gym "]},
        {"address_line1": "  12   Private\tStreet "},
    ],
)
def test_equivalent_values_hash_identically(overrides):
    assert _hash(_prop(**overrides)) == _hash(_prop())


def test_the_salt_blocks_dictionary_attacks():
    payload = hashing.build_payload(_prop())
    assert hashing.record_hash(payload, SALT) != hashing.record_hash(payload, "0x" + "cd" * 32)
    assert hashing.new_salt() != hashing.new_salt() and len(hashing.new_salt()) == 66


def test_floats_are_refused_because_their_text_is_unstable():
    with pytest.raises(TypeError):
        hashing.normalize_value(1.1)


def test_payload_is_not_leaked_by_the_key():
    key = hashing.property_key("abc")
    assert key == hashing.property_key("abc") != hashing.property_key("abd")
    assert "abc" not in key


def test_changed_fields_lists_the_differences():
    committed = hashing.build_payload(_prop())
    current = hashing.build_payload(_prop(city="Other", bedrooms=9))
    assert hashing.changed_fields(committed, current) == ["bedrooms", "city"]
    assert hashing.changed_fields(None, current) == []
