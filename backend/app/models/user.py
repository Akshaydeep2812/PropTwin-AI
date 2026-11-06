import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Index, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import CreatedAt, UTCDateTime, UpdatedAt, UuidPK

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UuidPK]
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    wallet_address: Mapped[Optional[str]] = mapped_column(String(42), unique=True)
    wallet_nonce: Mapped[Optional[str]] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users", lazy="selectin")
    properties: Mapped[list["Property"]] = relationship(back_populates="owner")  # noqa: F821

    @property
    def role_names(self) -> list[str]:
        return sorted(role.name for role in self.roles)

    def has_role(self, *names: str) -> bool:
        return any(role.name in names for role in self.roles)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UuidPK]
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_revoked", "user_id", "revoked_at"),)

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    rotated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]


class AccountToken(Base):
    """Single-use email verification and password reset tokens, stored only as hashes."""

    __tablename__ = "account_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_account_tokens_purpose"),)

    id: Mapped[UuidPK]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]
