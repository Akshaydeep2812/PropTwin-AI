from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DatabaseSession, OptionalUser
from app.core.config import get_settings
from app.core.errors import not_found
from app.models import BlockchainTransaction, OwnershipTransfer, Valuation
from app.schemas.blockchain import (
    HistoryRead,
    NetworkStatus,
    RecordRead,
    SubmitHash,
    TransactionRead,
    TransferCancelResult,
    TransferCreate,
    TransferRead,
    TransferWithCall,
    VerificationResult,
)
from app.services import access, blockchain_service, valuation_service

router = APIRouter(prefix="/blockchain", tags=["blockchain"])


def _with_call(transfer: OwnershipTransfer, transaction: BlockchainTransaction) -> dict:
    return {
        "transfer": transfer,
        "call": {
            "transaction_id": transaction.id,
            "to": transaction.contract_address,
            "data": transaction.call_data,
            "from_address": transaction.from_address,
            "chain_id": get_settings().blockchain_chain_id,
        },
    }


@router.get("/network", response_model=NetworkStatus)
def network() -> dict:
    return blockchain_service.network_status()


@router.post("/properties/{property_id}/register", response_model=TransactionRead, status_code=status.HTTP_202_ACCEPTED)
def register_property(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    """Accepted means submitted, not confirmed. Clients watch the transaction until it settles."""
    return blockchain_service.commit_record(db, access.get_managed(db, property_id, user), user)


@router.post("/properties/{property_id}/assign-controller", response_model=TransactionRead, status_code=status.HTTP_202_ACCEPTED)
def assign_controller(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    return blockchain_service.assign_controller_to_owner_wallet(db, access.get_managed(db, property_id, user), user)


@router.post("/properties/{property_id}/verify", response_model=VerificationResult)
def verify_property(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return blockchain_service.verify_record(db, access.get_for_review(db, property_id, user))


@router.get("/properties/{property_id}/history", response_model=HistoryRead)
def property_history(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return blockchain_service.history(db, access.get_for_review(db, property_id, user))


@router.get("/properties/{property_id}/record", response_model=RecordRead)
def public_record(property_id: UUID, db: DatabaseSession, user: OptionalUser):
    prop = access.get_visible(db, property_id, user)
    record = blockchain_service._record_for(db, prop.id)
    if record is None or record.record_version == 0:
        raise not_found("Blockchain record")
    return record


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: UUID, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    return blockchain_service.get_transaction(db, transaction_id, user)


@router.post("/transactions/{transaction_id}/submit", response_model=TransactionRead)
def submit_transaction(transaction_id: UUID, payload: SubmitHash, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    return blockchain_service.submit_wallet_transaction(db, transaction_id, user, payload.tx_hash)


@router.post("/transactions/{transaction_id}/abandon", response_model=TransactionRead)
def abandon_transaction(transaction_id: UUID, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    return blockchain_service.abandon_wallet_transaction(db, transaction_id, user)


@router.get("/ownership-transfer", response_model=list[TransferRead])
def list_transfers(user: CurrentUser, db: DatabaseSession) -> list[OwnershipTransfer]:
    return blockchain_service.list_transfers(db, user)


@router.post("/ownership-transfer", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def create_transfer(payload: TransferCreate, user: CurrentUser, db: DatabaseSession) -> OwnershipTransfer:
    return blockchain_service.create_transfer(db, payload.property_id, user, None if payload.recipient_email is None else str(payload.recipient_email))


@router.post("/ownership-transfer/{transfer_id}/propose", response_model=TransferWithCall)
def propose_transfer(transfer_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return _with_call(*blockchain_service.prepare_proposal(db, transfer_id, user))


@router.post("/ownership-transfer/{transfer_id}/accept", response_model=TransferWithCall)
def accept_transfer(transfer_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    return _with_call(*blockchain_service.prepare_acceptance(db, transfer_id, user))


@router.post("/ownership-transfer/{transfer_id}/cancel", response_model=TransferCancelResult)
def cancel_transfer(transfer_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    transfer, transaction = blockchain_service.cancel_transfer(db, transfer_id, user)
    return {"transfer": transfer, "call": None} if transaction is None else _with_call(transfer, transaction)


@router.post("/valuations/{valuation_id}/commit", response_model=TransactionRead, status_code=status.HTTP_202_ACCEPTED)
def commit_valuation(valuation_id: UUID, user: CurrentUser, db: DatabaseSession) -> BlockchainTransaction:
    valuation = db.get(Valuation, valuation_id)
    if valuation is None or not valuation_service.can_read(db, valuation, user):
        raise not_found("Valuation")
    return blockchain_service.commit_valuation(db, valuation, user)
