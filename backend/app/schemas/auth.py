import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    # Verifier and admin are deliberately absent: they can only be granted by an admin.
    role: Literal["owner", "investor"] = "owner"

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be blank.")
        return normalized


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class DemoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class DemoAccount(BaseModel):
    email: EmailStr
    display_name: str
    roles: list[str] = Field(validation_alias="role_names")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    phone: str | None = None
    wallet_address: str | None = None
    roles: list[str] = Field(validation_alias="role_names")
    email_verified_at: datetime | None = None
    is_active: bool
    is_demo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class TokenConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=200)


class PasswordResetConfirm(TokenConfirm):
    new_password: str = Field(min_length=12, max_length=128)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30, pattern=r"^[0-9+()\- ]*$")


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class WalletChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")


class WalletChallengeResponse(BaseModel):
    message: str


class WalletLink(WalletChallengeRequest):
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")


class MessageResponse(BaseModel):
    message: str
    delivery: str | None = None
