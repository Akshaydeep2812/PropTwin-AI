from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token, hash_password, hash_token, verify_password

PROD = {"app_env": "production", "secret_key": "x" * 40, "cookie_secure": True, "_env_file": None}


def test_password_hash_uses_argon2_and_verifies():
    hashed = hash_password("correct-horse-battery")
    assert hashed.startswith("$argon2") and verify_password("correct-horse-battery", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_round_trip():
    user_id, session_id = uuid4(), uuid4()
    assert decode_access_token(create_access_token(user_id, session_id)) == (user_id, session_id)


def test_hash_token_is_stable_and_not_the_input():
    assert hash_token("abc") == hash_token("abc") != "abc"


def test_production_refuses_placeholder_secret():
    with pytest.raises(ValueError):
        Settings(**{**PROD, "secret_key": "development-only-change-me"})


def test_production_requires_secure_cookies():
    with pytest.raises(ValueError):
        Settings(**{**PROD, "cookie_secure": False})


def test_production_refuses_public_hardhat_key():
    with pytest.raises(ValueError):
        Settings(**PROD, blockchain_relayer_private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
