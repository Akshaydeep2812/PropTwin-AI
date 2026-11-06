"""Application rules for chain records: who may commit what, and when a transaction counts as confirmed."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain import hashing
from app.blockchain.gateway import ChainGateway, ChainRejected, ChainUnavailable, get_gateway
from app.core.config import get_settings
from app.core.errors import AppError, conflict, forbidden, not_found
from app.models import BlockchainEvent, BlockchainRecord, BlockchainTransaction, OwnershipTransfer, Property, PropertyOwnershipHistory, User, Valuation
from app.models.types import utcnow
from app.services import access, audit
from app.services.notifications import notify

OPEN_STATUSES = ("pending", "submitted")
DROPPED_AFTER = timedelta(minutes=30)
LEGAL_NOTE = "A blockchain record is a tamper-evident commitment. It does not establish legal ownership or prove that the underlying documents are authentic."
TRANSFER_NOTE = "This moves control of the on-chain record and the application record. It does not transfer legal title to the property."


def _gateway() -> ChainGateway:
    try:
        return get_gateway()
    except ChainUnavailable as exc:
        raise AppError(503, "blockchain_unavailable", str(exc)) from exc


def network_status() -> dict[str, Any]:
    settings = get_settings()
    try:
        gateway = get_gateway()
    except ChainUnavailable as exc:
        return {"configured": False, "reachable": False, "network": settings.blockchain_network_name, "chain_id": settings.blockchain_chain_id, "contract_address": settings.blockchain_contract_address, "required_confirmations": settings.blockchain_confirmations, "detail": str(exc)}
    return {
        "configured": True,
        "reachable": gateway.is_reachable(),
        "network": gateway.network,
        "chain_id": settings.blockchain_chain_id,
        "contract_address": gateway.contract_address,
        "required_confirmations": settings.blockchain_confirmations,
        "detail": None,
    }


def _record_for(db: Session, property_id: uuid.UUID) -> BlockchainRecord | None:
    return db.scalar(select(BlockchainRecord).where(BlockchainRecord.property_id == property_id))


def _assert_no_open_transaction(db: Session, property_id: uuid.UUID) -> None:
    # The row lock serializes commits for one property, so version numbers cannot collide.
    db.scalar(select(Property.id).where(Property.id == property_id).with_for_update())
    open_tx = db.scalar(
        select(BlockchainTransaction.id).where(BlockchainTransaction.property_id == property_id, BlockchainTransaction.status.in_(OPEN_STATUSES)).limit(1)
    )
    if open_tx:
        raise conflict("transaction_in_progress", "This property already has a blockchain transaction in progress.")


def _new_transaction(db: Session, gateway: ChainGateway, prop: Property, user: User, operation: str, signing_mode: str, call_data: str, **extra: Any) -> BlockchainTransaction:
    transaction = BlockchainTransaction(
        property_id=prop.id,
        initiated_by_id=user.id,
        network=gateway.network,
        contract_address=gateway.contract_address,
        operation=operation,
        signing_mode=signing_mode,
        call_data=call_data,
        required_confirmations=get_settings().blockchain_confirmations,
        **extra,
    )
    db.add(transaction)
    db.flush()
    return transaction


def _send_with_relayer(db: Session, gateway: ChainGateway, transaction: BlockchainTransaction) -> None:
    """Records the outcome of submitting. A failure here is stored and shown, never reported as success."""
    try:
        tx_hash = gateway.send_as_relayer(transaction.call_data)
    except ChainRejected as exc:
        transaction.status = "failed"
        transaction.failure_reason = f"Rejected by the node before submission: {exc}"
    except ChainUnavailable as exc:
        transaction.status = "failed"
        transaction.failure_reason = str(exc)
    else:
        transaction.tx_hash = tx_hash
        transaction.from_address = gateway.relayer_address
        transaction.status = "submitted"
        transaction.submitted_at = utcnow()


def commit_record(db: Session, prop: Property, user: User) -> BlockchainTransaction:
    """Registers the property, or commits its current state as a new version if already registered."""
    gateway = _gateway()
    _assert_no_open_transaction(db, prop.id)
    record = _record_for(db, prop.id)
    payload_salt = record.salt if record else hashing.new_salt()
    key = record.property_key if record else hashing.property_key(prop.id)
    payload = hashing.build_payload(prop)
    new_hash = hashing.record_hash(payload, payload_salt)

    if record is not None and record.record_version > 0 and record.record_hash == new_hash:
        raise conflict("record_unchanged", "The on-chain record already matches this property.")

    if record is None:
        record = BlockchainRecord(
            property_id=prop.id,
            property_key=key,
            salt=payload_salt,
            hash_version=hashing.HASH_VERSION,
            network=gateway.network,
            contract_address=gateway.contract_address,
        )
        db.add(record)
        db.flush()

    if record.record_version == 0:
        # A record is held by the owner's own wallet when linked, otherwise by the application's relayer.
        controller = user.wallet_address or gateway.relayer_address
        if controller is None:
            raise AppError(503, "blockchain_unavailable", "No relayer key is configured.")
        operation, version = "register", 1
        call_data = gateway.encode_call("register", key, new_hash, controller)
    else:
        operation, version = "update", record.record_version + 1
        call_data = gateway.encode_call("updateRecord", key, new_hash, record.record_version)

    transaction = _new_transaction(db, gateway, prop, user, operation, "relayer", call_data, record_hash=new_hash, record_version=version, committed_payload=payload)
    _send_with_relayer(db, gateway, transaction)
    audit.record(db, f"blockchain.{operation}", "blockchain_transaction", transaction.id, actor_id=user.id, property_id=str(prop.id), status=transaction.status)
    db.commit()
    db.refresh(transaction)
    return transaction


def assign_controller_to_owner_wallet(db: Session, prop: Property, user: User) -> BlockchainTransaction:
    """Moves a relayer-held record to the owner's own wallet, which transfers need."""
    gateway = _gateway()
    if not user.wallet_address:
        raise AppError(422, "wallet_required", "Link a wallet to your profile first.")
    _assert_no_open_transaction(db, prop.id)
    record = _record_for(db, prop.id)
    if record is None or record.record_version == 0:
        raise AppError(422, "not_registered", "Register this property on the blockchain first.")
    call_data = gateway.encode_call("assignController", record.property_key, user.wallet_address)
    transaction = _new_transaction(db, gateway, prop, user, "update", "relayer", call_data)
    _send_with_relayer(db, gateway, transaction)
    audit.record(db, "blockchain.assign_controller", "blockchain_transaction", transaction.id, actor_id=user.id, property_id=str(prop.id))
    db.commit()
    db.refresh(transaction)
    return transaction


def submit_wallet_transaction(db: Session, transaction_id: uuid.UUID, user: User, tx_hash: str) -> BlockchainTransaction:
    """A client's claimed hash is not trusted: it must be this exact call, from this user's wallet, to this contract."""
    gateway = _gateway()
    transaction = db.scalar(select(BlockchainTransaction).where(BlockchainTransaction.id == transaction_id).with_for_update())
    if transaction is None or transaction.initiated_by_id != user.id:
        raise not_found("Transaction")
    if transaction.signing_mode != "wallet":
        raise AppError(422, "not_a_wallet_transaction", "This transaction is signed by the server.")
    if transaction.status != "pending":
        raise conflict("transaction_already_submitted", "A hash has already been recorded for this transaction.")
    try:
        on_chain = gateway.get_transaction(tx_hash)
    except ChainUnavailable as exc:
        raise AppError(503, "blockchain_unavailable", str(exc)) from exc
    if on_chain is None:
        raise AppError(422, "transaction_not_found", "That transaction hash was not found on this network.")
    if on_chain.to is None or Web3.to_checksum_address(on_chain.to) != gateway.contract_address:
        raise AppError(422, "wrong_contract", "That transaction was not sent to the registry contract.")
    if on_chain.sender != user.wallet_address or on_chain.sender != transaction.from_address:
        raise AppError(422, "wrong_sender", "That transaction was not sent from your linked wallet.")
    if on_chain.data.lower() != transaction.call_data.lower():
        raise AppError(422, "wrong_call_data", "That transaction does not contain the prepared call.")
    transaction.tx_hash = tx_hash
    transaction.status = "submitted"
    transaction.submitted_at = utcnow()
    audit.record(db, "blockchain.wallet_submitted", "blockchain_transaction", transaction.id, actor_id=user.id, tx_hash=tx_hash)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("hash_already_used", "That transaction hash is already recorded.") from exc
    db.refresh(transaction)
    return transaction


def refresh_transaction(db: Session, transaction: BlockchainTransaction, gateway: ChainGateway | None = None) -> BlockchainTransaction:
    """The only code that can mark a transaction confirmed, and only from a receipt meeting the confirmation policy."""
    if transaction.status != "submitted" or not transaction.tx_hash:
        return transaction
    gateway = gateway or get_gateway()
    receipt = gateway.get_receipt(transaction.tx_hash)
    if receipt is None:
        if transaction.submitted_at and utcnow() - transaction.submitted_at > DROPPED_AFTER and gateway.get_transaction(transaction.tx_hash) is None:
            transaction.status = "failed"
            transaction.failure_reason = "The network no longer knows this transaction; it appears to have been dropped."
            _on_failure(db, transaction)
            db.commit()
        return transaction

    transaction.block_number = receipt.block_number
    if not receipt.succeeded:
        transaction.status = "reverted"
        transaction.failure_reason = "The transaction was mined but reverted by the contract."
        _on_failure(db, transaction)
        db.commit()
        return transaction

    transaction.confirmations = max(0, gateway.latest_block() - receipt.block_number + 1)
    if transaction.confirmations < transaction.required_confirmations:
        db.commit()
        return transaction

    transaction.status = "confirmed"
    transaction.confirmed_at = utcnow()
    known = {event.log_index for event in transaction.events}
    for event in gateway.decode_events(receipt):
        if event["log_index"] not in known:
            db.add(BlockchainEvent(transaction_id=transaction.id, event_name=event["name"], log_index=event["log_index"], block_number=event["block_number"], args=_json_safe(event["args"])))
    _on_confirmed(db, transaction, gateway)
    audit.record(db, "blockchain.confirmed", "blockchain_transaction", transaction.id, operation=transaction.operation, tx_hash=transaction.tx_hash, block_number=receipt.block_number)
    notify(db, transaction.initiated_by_id, "blockchain_confirmed", f"Blockchain {transaction.operation} confirmed", f"Transaction {transaction.tx_hash}", f"/properties/{transaction.property_id}/blockchain")
    db.commit()
    db.expire(transaction, ["events"])
    return transaction


def _json_safe(args: dict) -> dict:
    return {key: (value if isinstance(value, (str, bool, type(None))) else str(value)) for key, value in args.items()}


def _on_confirmed(db: Session, transaction: BlockchainTransaction, gateway: ChainGateway) -> None:
    record = _record_for(db, transaction.property_id)
    if transaction.operation in ("register", "update") and transaction.record_hash and record is not None:
        record.record_hash = transaction.record_hash
        record.record_version = transaction.record_version
        record.committed_payload = transaction.committed_payload
    if record is not None:
        on_chain = gateway.get_record(record.property_key)
        if on_chain is not None:
            record.controller_address = on_chain.controller

    transfer = db.scalar(
        select(OwnershipTransfer).where(
            (OwnershipTransfer.propose_tx_id == transaction.id) | (OwnershipTransfer.accept_tx_id == transaction.id) | (OwnershipTransfer.cancel_tx_id == transaction.id)
        )
    )
    if transfer is None:
        return
    if transaction.operation == "propose_transfer":
        transfer.status = "proposed"
        notify(db, transfer.to_user_id, "transfer_proposed", "A property transfer awaits your acceptance", TRANSFER_NOTE, f"/transfers/{transfer.id}")
    elif transaction.operation == "accept_transfer":
        _complete_transfer(db, transfer)
    elif transaction.operation == "cancel_transfer":
        transfer.status = "cancelled"
        audit.record(db, "transfer.cancelled", "ownership_transfer", transfer.id, property_id=str(transfer.property_id), on_chain=True)
        notify(db, transfer.to_user_id, "transfer_cancelled", "A property transfer was cancelled", None, f"/transfers/{transfer.id}")


def _complete_transfer(db: Session, transfer: OwnershipTransfer) -> None:
    prop = access.load_property(db, transfer.property_id)
    now = utcnow()
    current = db.scalar(select(PropertyOwnershipHistory).where(PropertyOwnershipHistory.property_id == prop.id, PropertyOwnershipHistory.effective_to.is_(None)))
    if current is not None:
        current.effective_to = now
    db.add(PropertyOwnershipHistory(property_id=prop.id, owner_id=transfer.to_user_id, source="blockchain_transfer", effective_from=now))
    prop.owner_id = transfer.to_user_id
    transfer.status = "accepted"
    audit.record(db, "transfer.accepted", "ownership_transfer", transfer.id, from_user=str(transfer.from_user_id), to_user=str(transfer.to_user_id), property_id=str(prop.id))
    notify(db, transfer.from_user_id, "transfer_accepted", "Your property transfer was accepted", TRANSFER_NOTE, f"/transfers/{transfer.id}")


def _on_failure(db: Session, transaction: BlockchainTransaction) -> None:
    notify(db, transaction.initiated_by_id, "blockchain_failed", f"Blockchain {transaction.operation} did not succeed", transaction.failure_reason, f"/properties/{transaction.property_id}/blockchain")


def reconcile_open_transactions(db: Session) -> None:
    """Runs in the worker, so a status still settles if the user closed the page."""
    try:
        gateway = get_gateway()
    except ChainUnavailable:
        return
    for transaction in db.scalars(select(BlockchainTransaction).where(BlockchainTransaction.status == "submitted").limit(100)).all():
        try:
            refresh_transaction(db, transaction, gateway)
        except ChainUnavailable:
            db.rollback()
            return


def get_transaction(db: Session, transaction_id: uuid.UUID, user: User) -> BlockchainTransaction:
    transaction = db.get(BlockchainTransaction, transaction_id)
    if transaction is None:
        raise not_found("Transaction")
    prop = access.load_property(db, transaction.property_id)
    if transaction.initiated_by_id != user.id and not access.can_view_full(db, user, prop):
        raise not_found("Transaction")
    try:
        return refresh_transaction(db, transaction)
    except ChainUnavailable:
        return transaction


def verify_record(db: Session, prop: Property) -> dict[str, Any]:
    """Compares three things: the live record's hash, the hash the app stored, and the hash on the chain."""
    record = _record_for(db, prop.id)
    current_payload = hashing.build_payload(prop)
    base: dict[str, Any] = {"property_id": prop.id, "hash_version": hashing.HASH_VERSION, "covered_fields": list(hashing.COVERED_FIELDS), "legal_note": LEGAL_NOTE, "checked_at": utcnow()}
    if record is None or record.record_version == 0:
        return {**base, "result": "not_registered", "matches": False, "detail": "This property has no confirmed blockchain record yet."}

    recalculated = hashing.record_hash(current_payload, record.salt)
    base.update(
        property_key=record.property_key,
        record_version=record.record_version,
        recalculated_hash=recalculated,
        network=record.network,
        contract_address=record.contract_address,
        controller_address=record.controller_address,
    )
    gateway = _gateway()
    try:
        on_chain = gateway.get_record(record.property_key)
    except ChainUnavailable as exc:
        return {**base, "result": "chain_unavailable", "matches": False, "detail": str(exc)}
    if on_chain is None:
        return {**base, "result": "missing_on_chain", "matches": False, "detail": "The application has a record, but the contract does not. The network may have been reset."}

    base.update(on_chain_hash=on_chain.record_hash, on_chain_version=on_chain.version)
    if on_chain.record_hash.lower() == recalculated.lower():
        return {**base, "result": "match", "matches": True, "detail": "The current off-chain record matches the hash stored on-chain."}
    return {
        **base,
        "result": "mismatch",
        "matches": False,
        "changed_fields": hashing.changed_fields(record.committed_payload, current_payload),
        "detail": "The current off-chain record differs from what was committed. This is expected after a legitimate edit that has not been committed yet.",
    }


def history(db: Session, prop: Property) -> dict[str, Any]:
    transactions = db.scalars(select(BlockchainTransaction).where(BlockchainTransaction.property_id == prop.id).order_by(BlockchainTransaction.created_at.desc())).all()
    return {"record": _record_for(db, prop.id), "transactions": list(transactions), "legal_note": LEGAL_NOTE}


def _resolve_user_by_email(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active:
        raise not_found("Recipient")
    return user


def create_transfer(db: Session, prop_id: uuid.UUID, user: User, recipient_email: str | None) -> OwnershipTransfer:
    """An owner names a recipient. An investor asks for a listed property, which the owner must then propose."""
    prop = access.get_visible(db, prop_id, user)
    is_owner = access.is_owner_or_admin(user, prop) and prop.owner_id == user.id
    if is_owner:
        if not recipient_email:
            raise AppError(422, "recipient_required", "Name the account that should receive the transfer.")
        recipient = _resolve_user_by_email(db, recipient_email)
    elif user.has_role("investor") and access.is_public(prop):
        recipient = user
    else:
        raise forbidden()
    if recipient.id == prop.owner_id:
        raise AppError(422, "invalid_recipient", "A property cannot be transferred to its current owner.")
    if not recipient.wallet_address:
        if not is_owner:
            raise AppError(422, "wallet_required", "Link a wallet to your profile before requesting a transfer.")
        raise AppError(422, "recipient_wallet_required", "The recipient has not linked a wallet yet.")
    record = _record_for(db, prop.id)
    if record is None or record.record_version == 0:
        raise AppError(422, "not_registered", "This property must be registered on the blockchain before a transfer.")
    open_transfer = db.scalar(select(OwnershipTransfer.id).where(OwnershipTransfer.property_id == prop.id, OwnershipTransfer.status.in_(("requested", "proposed"))).limit(1))
    if open_transfer:
        raise conflict("transfer_in_progress", "This property already has a transfer in progress.")
    transfer = OwnershipTransfer(property_id=prop.id, from_user_id=prop.owner_id, to_user_id=recipient.id, to_address=recipient.wallet_address, status="requested")
    db.add(transfer)
    db.flush()
    audit.record(db, "transfer.requested", "ownership_transfer", transfer.id, actor_id=user.id, property_id=str(prop.id))
    if not is_owner:
        notify(db, prop.owner_id, "transfer_requested", f"Transfer requested: {prop.title}", TRANSFER_NOTE, f"/transfers/{transfer.id}")
    db.commit()
    db.refresh(transfer)
    return transfer


def _get_transfer(db: Session, transfer_id: uuid.UUID) -> OwnershipTransfer:
    transfer = db.scalar(select(OwnershipTransfer).where(OwnershipTransfer.id == transfer_id).with_for_update())
    if transfer is None:
        raise not_found("Transfer")
    return transfer


def prepare_proposal(db: Session, transfer_id: uuid.UUID, user: User) -> tuple[OwnershipTransfer, BlockchainTransaction]:
    gateway = _gateway()
    transfer = _get_transfer(db, transfer_id)
    if user.id not in (transfer.from_user_id, transfer.to_user_id):
        raise not_found("Transfer")
    if user.id != transfer.from_user_id:
        raise forbidden("Only the current owner can propose this transfer.")
    if transfer.status != "requested":
        raise conflict("invalid_transfer_state", f"A transfer that is {transfer.status} cannot be proposed.")
    prop = access.load_property(db, transfer.property_id)
    record = _record_for(db, prop.id)
    if record is None:
        raise AppError(422, "not_registered", "This property is not registered on the blockchain.")
    if not user.wallet_address:
        raise AppError(422, "wallet_required", "Link a wallet to your profile first.")
    on_chain = gateway.get_record(record.property_key)
    if on_chain is None or on_chain.controller != user.wallet_address:
        raise AppError(409, "not_controller", "Your linked wallet does not control this record on-chain. Assign it to your wallet first.")
    _assert_no_open_transaction(db, prop.id)
    call_data = gateway.encode_call("proposeTransfer", record.property_key, transfer.to_address)
    transaction = _new_transaction(db, gateway, prop, user, "propose_transfer", "wallet", call_data, from_address=user.wallet_address)
    transfer.propose_tx_id = transaction.id
    audit.record(db, "transfer.propose_prepared", "ownership_transfer", transfer.id, actor_id=user.id)
    db.commit()
    db.refresh(transaction)
    return transfer, transaction


def prepare_acceptance(db: Session, transfer_id: uuid.UUID, user: User) -> tuple[OwnershipTransfer, BlockchainTransaction]:
    gateway = _gateway()
    transfer = _get_transfer(db, transfer_id)
    if user.id not in (transfer.from_user_id, transfer.to_user_id):
        raise not_found("Transfer")
    if user.id != transfer.to_user_id:
        raise forbidden("Only the proposed recipient can accept this transfer.")
    if transfer.status != "proposed":
        raise conflict("invalid_transfer_state", f"A transfer that is {transfer.status} cannot be accepted.")
    if user.wallet_address != transfer.to_address:
        raise AppError(409, "wallet_changed", "Your linked wallet is not the address named in this transfer.")
    prop = access.load_property(db, transfer.property_id)
    record = _record_for(db, prop.id)
    _assert_no_open_transaction(db, prop.id)
    call_data = gateway.encode_call("acceptTransfer", record.property_key)
    transaction = _new_transaction(db, gateway, prop, user, "accept_transfer", "wallet", call_data, from_address=user.wallet_address)
    transfer.accept_tx_id = transaction.id
    audit.record(db, "transfer.accept_prepared", "ownership_transfer", transfer.id, actor_id=user.id)
    db.commit()
    db.refresh(transaction)
    return transfer, transaction


def cancel_transfer(db: Session, transfer_id: uuid.UUID, user: User) -> tuple[OwnershipTransfer, BlockchainTransaction | None]:
    """A request nothing has been signed for just closes. A proposal is live on-chain, so its controller must sign the cancellation."""
    transfer = _get_transfer(db, transfer_id)
    if user.id not in (transfer.from_user_id, transfer.to_user_id):
        raise not_found("Transfer")
    if transfer.status == "requested":
        transfer.status = "cancelled"
        other = transfer.to_user_id if user.id == transfer.from_user_id else transfer.from_user_id
        audit.record(db, "transfer.cancelled", "ownership_transfer", transfer.id, actor_id=user.id, on_chain=False)
        notify(db, other, "transfer_cancelled", "A property transfer request was cancelled", None, f"/transfers/{transfer.id}")
        db.commit()
        db.refresh(transfer)
        return transfer, None
    if transfer.status != "proposed":
        raise conflict("invalid_transfer_state", f"A transfer that is {transfer.status} cannot be cancelled.")
    if user.id != transfer.from_user_id:
        raise forbidden("Only the current owner can cancel a proposal on-chain. You can simply not accept it.")
    gateway = _gateway()
    if not user.wallet_address:
        raise AppError(422, "wallet_required", "Link a wallet to your profile first.")
    prop = access.load_property(db, transfer.property_id)
    record = _record_for(db, prop.id)
    _assert_no_open_transaction(db, prop.id)
    call_data = gateway.encode_call("cancelTransfer", record.property_key)
    transaction = _new_transaction(db, gateway, prop, user, "cancel_transfer", "wallet", call_data, from_address=user.wallet_address)
    transfer.cancel_tx_id = transaction.id
    audit.record(db, "transfer.cancel_prepared", "ownership_transfer", transfer.id, actor_id=user.id)
    db.commit()
    db.refresh(transaction)
    return transfer, transaction


def commit_valuation(db: Session, valuation: Valuation, user: User) -> BlockchainTransaction:
    """Records a salted commitment to one estimate, so that it can later be shown to be unchanged. The value stays off-chain."""
    gateway = _gateway()
    if valuation.property_id is None:
        raise AppError(422, "valuation_has_no_property", "Only estimates of a registered property can be committed.")
    prop = access.get_managed(db, valuation.property_id, user)
    record = _record_for(db, prop.id)
    if record is None or record.record_version == 0:
        raise AppError(422, "not_registered", "Register this property on the blockchain first.")
    _assert_no_open_transaction(db, prop.id)
    commitment = hashing.valuation_commitment(valuation.id, valuation.predicted_value, valuation.model_version.version, record.salt)
    call_data = gateway.encode_call("commitValuation", record.property_key, commitment)
    transaction = _new_transaction(db, gateway, prop, user, "commit_valuation", "relayer", call_data, record_hash=commitment)
    _send_with_relayer(db, gateway, transaction)
    audit.record(db, "blockchain.commit_valuation", "blockchain_transaction", transaction.id, actor_id=user.id, valuation_id=str(valuation.id), status=transaction.status)
    db.commit()
    db.refresh(transaction)
    return transaction


def abandon_wallet_transaction(db: Session, transaction_id: uuid.UUID, user: User) -> BlockchainTransaction:
    """Clears a prepared call the wallet never sent, so that it does not block the property's next transaction."""
    transaction = db.scalar(select(BlockchainTransaction).where(BlockchainTransaction.id == transaction_id).with_for_update())
    if transaction is None or transaction.initiated_by_id != user.id:
        raise not_found("Transaction")
    if transaction.signing_mode != "wallet" or transaction.status != "pending":
        raise conflict("cannot_abandon", "Only an unsent wallet transaction can be abandoned.")
    transaction.status = "failed"
    transaction.failure_reason = "Abandoned before it was signed."
    db.commit()
    db.refresh(transaction)
    return transaction


def list_transfers(db: Session, user: User) -> list[OwnershipTransfer]:
    return list(
        db.scalars(
            select(OwnershipTransfer)
            .where((OwnershipTransfer.from_user_id == user.id) | (OwnershipTransfer.to_user_id == user.id))
            .order_by(OwnershipTransfer.created_at.desc())
            .limit(100)
        )
    )
