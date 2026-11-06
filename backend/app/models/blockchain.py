import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import TRANSFER_STATUSES, TX_OPERATIONS, TX_STATUSES, CreatedAt, UTCDateTime, UpdatedAt, UuidPK, in_list


class BlockchainRecord(Base):
    """Latest commitment for a property. The salt stays off-chain to resist dictionary attacks."""

    __tablename__ = "blockchain_records"

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), unique=True, nullable=False)
    property_key: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
    salt: Mapped[str] = mapped_column(String(66), nullable=False)
    hash_version: Mapped[int] = mapped_column(Integer, nullable=False)
    record_hash: Mapped[Optional[str]] = mapped_column(String(66))
    record_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    controller_address: Mapped[Optional[str]] = mapped_column(String(42))
    network: Mapped[str] = mapped_column(String(50), nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class BlockchainTransaction(Base):
    __tablename__ = "blockchain_transactions"
    __table_args__ = (
        CheckConstraint(in_list("status", TX_STATUSES), name="ck_chain_tx_status"),
        CheckConstraint(in_list("operation", TX_OPERATIONS), name="ck_chain_tx_operation"),
        CheckConstraint("signing_mode IN ('relayer', 'wallet')", name="ck_chain_tx_signing_mode"),
        UniqueConstraint("network", "tx_hash", name="uq_chain_tx_network_hash"),
        Index("ix_chain_tx_status_created", "status", "created_at"),
    )

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    initiated_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    network: Mapped[str] = mapped_column(String(50), nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    signing_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    from_address: Mapped[Optional[str]] = mapped_column(String(42))
    call_data: Mapped[str] = mapped_column(Text, nullable=False)
    record_hash: Mapped[Optional[str]] = mapped_column(String(66))
    record_version: Mapped[Optional[int]] = mapped_column(Integer)
    committed_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    block_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    confirmations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_confirmations: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    events: Mapped[list["BlockchainEvent"]] = relationship(lazy="selectin", order_by="BlockchainEvent.log_index")


class BlockchainEvent(Base):
    __tablename__ = "blockchain_events"
    __table_args__ = (UniqueConstraint("transaction_id", "log_index", name="uq_chain_event_log"),)

    id: Mapped[UuidPK]
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("blockchain_transactions.id", ondelete="RESTRICT"), nullable=False)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    args: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[CreatedAt]


class OwnershipTransfer(Base):
    """Workflow for moving on-chain control. It does not transfer legal title."""

    __tablename__ = "ownership_transfers"
    __table_args__ = (
        CheckConstraint(in_list("status", TRANSFER_STATUSES), name="ck_transfer_status"),
        Index("ix_transfers_property_status", "property_id", "status"),
    )

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    from_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    to_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    propose_tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("blockchain_transactions.id", ondelete="RESTRICT"))
    accept_tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("blockchain_transactions.id", ondelete="RESTRICT"))
    cancel_tx_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("blockchain_transactions.id", ondelete="RESTRICT"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
