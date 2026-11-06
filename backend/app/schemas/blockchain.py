import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EventRead(BaseModel):
    event_name: str
    log_index: int
    block_number: int
    args: dict
    model_config = ConfigDict(from_attributes=True)


class TransactionRead(BaseModel):
    kind: Literal["blockchain_transaction"] = "blockchain_transaction"
    id: uuid.UUID
    property_id: uuid.UUID
    network: str
    contract_address: str
    tx_hash: str | None
    operation: str
    signing_mode: str
    initiated_by_id: uuid.UUID
    from_address: str | None
    status: str
    record_hash: str | None
    record_version: int | None
    block_number: int | None
    confirmations: int
    required_confirmations: int
    failure_reason: str | None
    submitted_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[EventRead]
    model_config = ConfigDict(from_attributes=True)


class RecordRead(BaseModel):
    """The salt and committed payload are private and are never returned."""

    property_id: uuid.UUID
    property_key: str
    hash_version: int
    record_hash: str | None
    record_version: int
    controller_address: str | None
    network: str
    contract_address: str
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HistoryRead(BaseModel):
    record: RecordRead | None
    transactions: list[TransactionRead]
    legal_note: str


class VerificationResult(BaseModel):
    property_id: uuid.UUID
    result: Literal["match", "mismatch", "not_registered", "missing_on_chain", "chain_unavailable"]
    matches: bool
    detail: str
    legal_note: str
    checked_at: datetime
    hash_version: int
    covered_fields: list[str]
    property_key: str | None = None
    record_version: int | None = None
    on_chain_version: int | None = None
    recalculated_hash: str | None = None
    on_chain_hash: str | None = None
    network: str | None = None
    contract_address: str | None = None
    controller_address: str | None = None
    changed_fields: list[str] = []


class NetworkStatus(BaseModel):
    configured: bool
    reachable: bool
    network: str
    chain_id: int
    contract_address: str | None
    required_confirmations: int
    detail: str | None


class SubmitHash(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tx_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID
    recipient_email: EmailStr | None = None


class TransferRead(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    to_address: str
    status: str
    propose_tx_id: uuid.UUID | None
    accept_tx_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    legal_note: str = "This moves control of the on-chain record and the application record. It does not transfer legal title to the property."
    model_config = ConfigDict(from_attributes=True)


class PreparedCall(BaseModel):
    """What the browser wallet signs. The server never sees the user's key."""

    transaction_id: uuid.UUID
    to: str
    data: str
    from_address: str
    chain_id: int


class TransferWithCall(BaseModel):
    transfer: TransferRead
    call: PreparedCall


class TransferCancelResult(BaseModel):
    """A call is present only when the cancellation must be signed on-chain."""

    transfer: TransferRead
    call: PreparedCall | None
