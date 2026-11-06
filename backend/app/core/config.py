from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# Well-known Hardhat development keys are public; they must never sign outside a local network.
PUBLIC_DEV_KEY_PREFIXES = ("ac0974be", "59c6995e", "5de4111a", "7c852118", "47e179ec")
PLACEHOLDER_SECRETS = {"development-only-change-me", "replace-with-a-long-random-local-secret"}


class Settings(BaseSettings):
    app_name: str = "PropTwin AI API"
    app_env: str = "development"
    database_url: str = "mysql+pymysql://proptwin:proptwin@localhost:3307/proptwin"
    secret_key: SecretStr = Field(
        default=SecretStr("development-only-change-me"),
        description="Application signing secret; provide a unique value outside development.",
    )
    cors_origins: list[str] = ["http://localhost:5173"]
    frontend_base_url: str = "http://localhost:5173"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False
    rate_limit_enabled: bool = True

    storage_dir: Path = REPO_ROOT / "storage"
    max_upload_bytes: int = 10 * 1024 * 1024

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "no-reply@proptwin.local"

    model_artifact_dir: Path = REPO_ROOT / "ml" / "artifacts"
    default_currency: str = "INR"

    blockchain_rpc_url: str | None = None
    blockchain_network_name: str = "hardhat-local"
    blockchain_chain_id: int = 31337
    blockchain_contract_address: str | None = None
    blockchain_abi_path: Path = REPO_ROOT / "blockchain" / "abi" / "PropertyRegistry.json"
    blockchain_relayer_private_key: SecretStr | None = None
    blockchain_confirmations: int = 1

    # One-click sign-in to the seeded demo accounts. Local demos only: production refuses to start with it on.
    demo_login_enabled: bool = False

    worker_enabled: bool = True
    worker_poll_seconds: float = 5.0
    job_max_attempts: int = 5
    audit_retention_days: int = 730

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
        if not self.is_production:
            return self
        secret = self.secret_key.get_secret_value()
        if secret in PLACEHOLDER_SECRETS or len(secret) < 32:
            raise ValueError("SECRET_KEY must be a unique value of at least 32 characters in production.")
        if self.demo_login_enabled:
            raise ValueError("DEMO_LOGIN_ENABLED must be false in production.")
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production.")
        if self.blockchain_relayer_private_key is not None:
            key = self.blockchain_relayer_private_key.get_secret_value().removeprefix("0x").lower()
            if key.startswith(PUBLIC_DEV_KEY_PREFIXES):
                raise ValueError("BLOCKCHAIN_RELAYER_PRIVATE_KEY is a public development key.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
