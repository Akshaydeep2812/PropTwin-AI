"""These tests send real transactions to a real local Hardhat node. Nothing about the chain is mocked."""

import json
import os
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from pydantic import SecretStr
from sqlalchemy import select
from web3 import HTTPProvider, Web3

from app.blockchain import gateway as gateway_module
from app.core.config import get_settings
from app.models import AuditLog, BlockchainRecord, Property, PropertyOwnershipHistory
from app.workers import runner
from tests.conftest import REPO_ROOT

CHAIN_DIR = REPO_ROOT / "blockchain"
HARDHAT = CHAIN_DIR / "node_modules" / "hardhat" / "internal" / "cli" / "bootstrap.js"
PORT = 8546
RPC_URL = f"http://127.0.0.1:{PORT}"
# Hardhat's documented default test mnemonic. Its keys are public and are only ever used on this throwaway node.
TEST_MNEMONIC = "test test test test test test test test test test test junk"
Account.enable_unaudited_hdwallet_features()


def _hd_account(index: int):
    return Account.from_mnemonic(TEST_MNEMONIC, account_path=f"m/44'/60'/0'/0/{index}")


def _rpc_ready() -> bool:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()
    try:
        urlopen(Request(RPC_URL, body, {"Content-Type": "application/json"}), timeout=2).read()
        return True
    except (URLError, OSError):
        return False


@pytest.fixture(scope="session")
def deployed_contract():
    if not HARDHAT.is_file():
        pytest.skip("Hardhat is not installed; run npm install in blockchain/.")
    node = subprocess.Popen(["node", str(HARDHAT), "node", "--port", str(PORT)], cwd=CHAIN_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if _rpc_ready():
                break
            time.sleep(0.5)
        else:
            pytest.fail("The Hardhat node did not start.")
        env = {**os.environ, "LOCAL_RPC_URL": RPC_URL, "HARDHAT_NETWORK": "localhost"}
        subprocess.run(["node", str(HARDHAT), "run", "scripts/deploy.ts", "--network", "localhost"], cwd=CHAIN_DIR, env=env, check=True, capture_output=True, timeout=300)
        yield json.loads((CHAIN_DIR / "deployments" / "localhost.json").read_text())["address"]
    finally:
        node.terminate()
        node.wait(timeout=20)


@pytest.fixture
def chain(deployed_contract, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "blockchain_rpc_url", RPC_URL)
    monkeypatch.setattr(settings, "blockchain_contract_address", deployed_contract)
    monkeypatch.setattr(settings, "blockchain_relayer_private_key", SecretStr(_hd_account(1).key.to_0x_hex()))
    monkeypatch.setattr(settings, "blockchain_confirmations", 1)
    gateway_module._cached_gateway.cache_clear()
    yield Web3(HTTPProvider(RPC_URL))
    gateway_module._cached_gateway.cache_clear()


def _link_wallet(actor, account) -> None:
    message = actor.post("/api/v1/users/me/wallet/challenge", json={"address": account.address}).json()["message"]
    signature = account.sign_message(encode_defunct(text=message)).signature.to_0x_hex()
    response = actor.post("/api/v1/users/me/wallet", json={"address": account.address, "signature": signature})
    assert response.status_code == 200, response.text


def _send_from_wallet(w3, account, to, data, **overrides) -> str:
    transaction = {
        "from": account.address, "to": to, "data": data, "chainId": 31337, "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "gas": 300000, "maxFeePerGas": w3.to_wei(10, "gwei"), "maxPriorityFeePerGas": w3.to_wei(1, "gwei"), **overrides,
    }
    return w3.eth.send_raw_transaction(account.sign_transaction(transaction).raw_transaction).to_0x_hex()


def _register(owner, prop) -> dict:
    response = owner.post(f"/api/v1/blockchain/properties/{prop['id']}/register")
    assert response.status_code == 202, response.text
    return response.json()


def _settle(actor, transaction_id) -> dict:
    return actor.get(f"/api/v1/blockchain/transactions/{transaction_id}").json()


def _registered(owner, prop) -> dict:
    return _settle(owner, _register(owner, prop)["id"])


def test_network_status_reports_a_reachable_chain(chain, client, deployed_contract):
    client.cookies.clear()
    body = client.get("/api/v1/blockchain/network").json()
    assert body["configured"] is True and body["reachable"] is True
    assert body["contract_address"] == deployed_contract and body["chain_id"] == 31337


def test_register_is_only_confirmed_from_a_real_receipt(chain, make_actor, make_property, deployed_contract):
    owner = make_actor()
    prop = make_property(owner)
    submitted = _register(owner, prop)
    assert submitted["status"] == "submitted" and submitted["confirmed_at"] is None
    assert submitted["tx_hash"].startswith("0x") and submitted["record_version"] == 1

    settled = _settle(owner, submitted["id"])
    assert settled["status"] == "confirmed" and settled["confirmations"] >= 1
    receipt = chain.eth.get_transaction_receipt(settled["tx_hash"])
    assert receipt["status"] == 1 and receipt["blockNumber"] == settled["block_number"]
    assert Web3.to_checksum_address(receipt["to"]) == deployed_contract
    assert [event["event_name"] for event in settled["events"]] == ["PropertyRegistered"]
    assert settled["events"][0]["args"]["recordHash"] == settled["record_hash"]


def test_confirmation_policy_is_enforced(chain, make_actor, make_property, monkeypatch):
    monkeypatch.setattr(get_settings(), "blockchain_confirmations", 2)
    owner = make_actor()
    transaction = _register(owner, make_property(owner))
    pending = _settle(owner, transaction["id"])
    assert pending["status"] == "submitted" and pending["confirmations"] == 1 and pending["required_confirmations"] == 2
    chain.provider.make_request("evm_mine", [])
    assert _settle(owner, transaction["id"])["status"] == "confirmed"


def test_worker_reconciles_without_anyone_polling(chain, make_actor, make_property, db):
    owner = make_actor()
    transaction = _register(owner, make_property(owner))
    runner.run_pass(db)
    history = owner.get(f"/api/v1/blockchain/transactions/{transaction['id']}").json()
    assert history["status"] == "confirmed"
    assert owner.get("/api/v1/notifications").json()["total"] == 1


def test_nothing_private_goes_on_chain_or_through_the_api(chain, make_actor, make_property):
    owner = make_actor()
    prop = make_property(owner, listing_status="listed")
    settled = _registered(owner, prop)
    transaction = chain.eth.get_transaction(settled["tx_hash"])
    calldata = bytes(transaction["input"])
    for secret in (b"12 Private Street", b"Riverside", b"500001", owner.user["email"].encode(), prop["id"].encode()):
        assert secret not in calldata
    history = owner.get(f"/api/v1/blockchain/properties/{prop['id']}/history").json()
    assert "salt" not in json.dumps(history) and "committed_payload" not in json.dumps(history)


def test_verify_detects_every_kind_of_difference(chain, make_actor, make_property, db):
    owner = make_actor()
    prop = make_property(owner)
    url = f"/api/v1/blockchain/properties/{prop['id']}/verify"
    assert owner.post(url).json()["result"] == "not_registered"

    _registered(owner, prop)
    matched = owner.post(url).json()
    assert matched["result"] == "match" and matched["matches"] is True
    assert matched["recalculated_hash"] == matched["on_chain_hash"]
    assert "does not establish legal ownership" in matched["legal_note"]

    # A legitimate edit is reported as uncommitted, naming the field.
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 5})
    edited = owner.post(url).json()
    assert edited["result"] == "mismatch" and edited["changed_fields"] == ["bedrooms"]

    # Direct database tampering is what this exists to catch: it bypasses the API, audit log, and twin.
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 2})
    assert owner.post(url).json()["result"] == "match"
    row = db.get(Property, __import__("uuid").UUID(prop["id"]))
    row.last_sale_price = 1
    db.commit()
    tampered = owner.post(url).json()
    assert tampered["result"] == "mismatch" and tampered["changed_fields"] == ["last_sale_price"]


def test_uncovered_edit_keeps_the_match(chain, make_actor, make_property):
    owner = make_actor()
    prop = make_property(owner)
    _registered(owner, prop)
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"title": "A better title", "asking_price": "9000000.00"})
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["result"] == "match"


def test_update_commits_a_new_version(chain, make_actor, make_property):
    owner = make_actor()
    prop = make_property(owner)
    _registered(owner, prop)
    register_url = f"/api/v1/blockchain/properties/{prop['id']}/register"
    unchanged = owner.post(register_url)
    assert unchanged.status_code == 409 and unchanged.json()["error"]["code"] == "record_unchanged"

    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 4})
    update = _settle(owner, owner.post(register_url).json()["id"])
    assert update["status"] == "confirmed" and update["operation"] == "update" and update["record_version"] == 2
    assert update["events"][0]["event_name"] == "RecordUpdated"
    verified = owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()
    assert verified["result"] == "match" and verified["on_chain_version"] == 2


def test_a_second_commit_waits_for_the_first(chain, make_actor, make_property, monkeypatch):
    monkeypatch.setattr(get_settings(), "blockchain_confirmations", 3)
    owner = make_actor()
    prop = make_property(owner)
    _register(owner, prop)
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 4})
    response = owner.post(f"/api/v1/blockchain/properties/{prop['id']}/register")
    assert response.status_code == 409 and response.json()["error"]["code"] == "transaction_in_progress"


def test_authorization(chain, make_actor, make_property, client):
    owner, stranger, verifier = make_actor(), make_actor(), make_actor("verifier")
    draft, listed = make_property(owner), make_property(owner, listing_status="listed")
    transaction = _registered(owner, listed)
    assert stranger.post(f"/api/v1/blockchain/properties/{draft['id']}/register").status_code == 404
    assert stranger.post(f"/api/v1/blockchain/properties/{listed['id']}/register").status_code == 403
    assert stranger.post(f"/api/v1/blockchain/properties/{listed['id']}/verify").status_code == 403
    assert verifier.post(f"/api/v1/blockchain/properties/{listed['id']}/register").status_code == 403
    assert stranger.get(f"/api/v1/blockchain/properties/{listed['id']}/history").status_code == 403
    assert stranger.get(f"/api/v1/blockchain/transactions/{transaction['id']}").status_code == 404
    client.cookies.clear()
    assert client.post(f"/api/v1/blockchain/properties/{listed['id']}/register").status_code == 401
    public = client.get(f"/api/v1/blockchain/properties/{listed['id']}/record")
    assert public.status_code == 200 and public.json()["record_version"] == 1
    assert "salt" not in public.json() and "committed_payload" not in public.json()
    assert client.get(f"/api/v1/blockchain/properties/{draft['id']}/record").status_code == 404


def test_dead_node_is_reported_as_failure_never_success(chain, make_actor, make_property, monkeypatch):
    monkeypatch.setattr(get_settings(), "blockchain_rpc_url", "http://127.0.0.1:1")
    gateway_module._cached_gateway.cache_clear()
    owner = make_actor()
    response = owner.post(f"/api/v1/blockchain/properties/{make_property(owner)['id']}/register")
    assert response.status_code == 202
    assert response.json()["status"] == "failed" and response.json()["tx_hash"] is None
    assert "unreachable" in response.json()["failure_reason"]


def test_unconfigured_chain_gives_a_clear_error(make_actor, make_property, monkeypatch, client):
    monkeypatch.setattr(get_settings(), "blockchain_rpc_url", None)
    gateway_module._cached_gateway.cache_clear()
    owner = make_actor()
    response = owner.post(f"/api/v1/blockchain/properties/{make_property(owner)['id']}/register")
    assert response.status_code == 503 and response.json()["error"]["code"] == "blockchain_unavailable"
    client.cookies.clear()
    assert client.get("/api/v1/blockchain/network").json()["configured"] is False


def _setup_transfer(chain, make_actor, make_property, listed=True):
    owner, buyer = make_actor(), make_actor("investor")
    owner_wallet, buyer_wallet = _hd_account(2), _hd_account(3)
    # Each test gets a fresh database but shares the chain, so wallets can repeat across tests.
    _link_wallet(owner, owner_wallet)
    _link_wallet(buyer, buyer_wallet)
    prop = make_property(owner, listing_status="listed" if listed else "draft")
    assert _registered(owner, prop)["status"] == "confirmed"
    return owner, buyer, owner_wallet, buyer_wallet, prop


def _propose(chain, owner, owner_wallet, prop, buyer) -> dict:
    created = owner.post("/api/v1/blockchain/ownership-transfer", json={"property_id": prop["id"], "recipient_email": buyer.user["email"]})
    assert created.status_code == 201, created.text
    prepared = owner.post(f"/api/v1/blockchain/ownership-transfer/{created.json()['id']}/propose").json()
    call = prepared["call"]
    tx_hash = _send_from_wallet(chain, owner_wallet, call["to"], call["data"])
    submitted = owner.post(f"/api/v1/blockchain/transactions/{call['transaction_id']}/submit", json={"tx_hash": tx_hash})
    assert submitted.status_code == 200, submitted.text
    assert _settle(owner, call["transaction_id"])["status"] == "confirmed"
    return created.json()


def test_full_two_step_transfer(chain, make_actor, make_property, db):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["controller_address"] == owner_wallet.address

    transfer = _propose(chain, owner, owner_wallet, prop, buyer)
    # A proposal alone must not move anything.
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["owner_id"] == owner.user["id"]
    assert buyer.get("/api/v1/notifications").json()["total"] >= 1

    accepted = buyer.post(f"/api/v1/blockchain/ownership-transfer/{transfer['id']}/accept").json()
    assert "does not transfer legal title" in accepted["transfer"]["legal_note"]
    call = accepted["call"]
    # The owner is unchanged until the receipt confirms, even after the wallet has sent the transaction.
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["owner_id"] == owner.user["id"]
    tx_hash = _send_from_wallet(chain, buyer_wallet, call["to"], call["data"])
    assert buyer.post(f"/api/v1/blockchain/transactions/{call['transaction_id']}/submit", json={"tx_hash": tx_hash}).status_code == 200
    assert _settle(buyer, call["transaction_id"])["events"][0]["event_name"] == "TransferAccepted"

    assert buyer.get(f"/api/v1/properties/{prop['id']}").json()["owner_id"] == buyer.user["id"]
    transfers = buyer.get("/api/v1/blockchain/ownership-transfer").json()
    assert transfers[0]["status"] == "accepted"
    assert owner.patch(f"/api/v1/properties/{prop['id']}", json={"title": "Not mine now"}).status_code == 403
    verified = buyer.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()
    assert verified["result"] == "match" and verified["controller_address"] == buyer_wallet.address

    history = db.scalars(select(PropertyOwnershipHistory).order_by(PropertyOwnershipHistory.effective_from)).all()
    assert [row.source for row in history] == ["registration", "blockchain_transfer"]
    assert history[0].effective_to is not None and history[1].effective_to is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "transfer.accepted")) is not None


def test_forged_hash_submissions_are_rejected(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    created = owner.post("/api/v1/blockchain/ownership-transfer", json={"property_id": prop["id"], "recipient_email": buyer.user["email"]}).json()
    call = owner.post(f"/api/v1/blockchain/ownership-transfer/{created['id']}/propose").json()["call"]
    submit = f"/api/v1/blockchain/transactions/{call['transaction_id']}/submit"

    def code(tx_hash: str) -> str:
        return owner.post(submit, json={"tx_hash": tx_hash}).json()["error"]["code"]

    assert code("0x" + "ab" * 32) == "transaction_not_found"
    assert code(_send_from_wallet(chain, owner_wallet, buyer_wallet.address, "0x")) == "wrong_contract"
    assert code(_send_from_wallet(chain, buyer_wallet, call["to"], call["data"])) == "wrong_sender"
    assert code(_send_from_wallet(chain, owner_wallet, call["to"], "0xdeadbeef", gas=100000)) == "wrong_call_data"
    assert buyer.post(submit, json={"tx_hash": "0x" + "ab" * 32}).status_code == 404
    assert _settle(owner, call["transaction_id"])["status"] == "pending"


def test_reverted_transaction_is_reported_and_changes_nothing(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    transfer = _propose(chain, owner, owner_wallet, prop, buyer)
    call = buyer.post(f"/api/v1/blockchain/ownership-transfer/{transfer['id']}/accept").json()["call"]
    # The owner cancels directly on-chain before the buyer's already-prepared acceptance lands.
    registry = gateway_module.get_gateway()
    key = owner.get(f"/api/v1/blockchain/properties/{prop['id']}/record").json()["property_key"]
    _send_from_wallet(chain, owner_wallet, call["to"], registry.encode_call("cancelTransfer", key))

    tx_hash = _send_from_wallet(chain, buyer_wallet, call["to"], call["data"])
    assert buyer.post(f"/api/v1/blockchain/transactions/{call['transaction_id']}/submit", json={"tx_hash": tx_hash}).status_code == 200
    settled = _settle(buyer, call["transaction_id"])
    assert settled["status"] == "reverted" and settled["confirmed_at"] is None and "reverted" in settled["failure_reason"]
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["owner_id"] == owner.user["id"]


def test_transfer_rules(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    url = "/api/v1/blockchain/ownership-transfer"
    other = make_actor("investor")
    assert owner.post(url, json={"property_id": prop["id"]}).json()["error"]["code"] == "recipient_required"
    assert owner.post(url, json={"property_id": prop["id"], "recipient_email": owner.user["email"]}).json()["error"]["code"] == "invalid_recipient"
    assert owner.post(url, json={"property_id": prop["id"], "recipient_email": other.user["email"]}).json()["error"]["code"] == "recipient_wallet_required"
    assert other.post(url, json={"property_id": prop["id"]}).json()["error"]["code"] == "wallet_required"
    assert make_actor().post(url, json={"property_id": prop["id"]}).status_code == 403

    # A buyer asks, but only the owner can propose, and only after that can the buyer accept.
    requested = buyer.post(url, json={"property_id": prop["id"]})
    assert requested.status_code == 201 and requested.json()["status"] == "requested"
    transfer_id = requested.json()["id"]
    assert owner.get("/api/v1/notifications").json()["total"] >= 1
    assert buyer.post(url, json={"property_id": prop["id"]}).status_code == 409
    assert buyer.post(f"{url}/{transfer_id}/propose").status_code == 403
    assert buyer.post(f"{url}/{transfer_id}/accept").json()["error"]["code"] == "invalid_transfer_state"
    assert other.post(f"{url}/{transfer_id}/accept").status_code == 404
    assert owner.post(f"{url}/{transfer_id}/accept").status_code == 403


def test_unsent_wallet_call_can_be_abandoned(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    created = owner.post("/api/v1/blockchain/ownership-transfer", json={"property_id": prop["id"], "recipient_email": buyer.user["email"]}).json()
    call = owner.post(f"/api/v1/blockchain/ownership-transfer/{created['id']}/propose").json()["call"]
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 4})
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/register").status_code == 409
    assert owner.post(f"/api/v1/blockchain/transactions/{call['transaction_id']}/abandon").json()["status"] == "failed"
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/register").status_code == 202


def test_relayer_held_record_needs_handover_before_transfer(chain, make_actor, make_property):
    owner, buyer = make_actor(), make_actor("investor")
    owner_wallet, buyer_wallet = _hd_account(2), _hd_account(3)
    prop = make_property(owner)
    _registered(owner, prop)
    _link_wallet(owner, owner_wallet)
    _link_wallet(buyer, buyer_wallet)
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["controller_address"] == _hd_account(1).address

    created = owner.post("/api/v1/blockchain/ownership-transfer", json={"property_id": prop["id"], "recipient_email": buyer.user["email"]}).json()
    refused = owner.post(f"/api/v1/blockchain/ownership-transfer/{created['id']}/propose")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_controller"

    handover = owner.post(f"/api/v1/blockchain/properties/{prop['id']}/assign-controller").json()
    assert _settle(owner, handover["id"])["events"][0]["event_name"] == "ControllerAssigned"
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["controller_address"] == owner_wallet.address
    assert owner.post(f"/api/v1/blockchain/ownership-transfer/{created['id']}/propose").status_code == 200


def test_chain_reset_is_detected(chain, make_actor, make_property, db, deployed_contract):
    owner = make_actor()
    prop = make_property(owner)
    _registered(owner, prop)
    record = db.scalar(select(BlockchainRecord))
    record.property_key = "0x" + "11" * 32
    db.commit()
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["result"] == "missing_on_chain"


def test_valuation_commitment_goes_on_chain_without_the_value(chain, make_actor, make_property, active_model, db):
    owner, stranger = make_actor(), make_actor()
    prop = make_property(owner, listing_status="listed")
    valuation = owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]}).json()
    url = f"/api/v1/blockchain/valuations/{valuation['id']}/commit"

    refused = owner.post(url)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "not_registered"
    _registered(owner, prop)
    assert stranger.post(url).status_code == 404

    settled = _settle(owner, owner.post(url).json()["id"])
    assert settled["status"] == "confirmed" and settled["operation"] == "commit_valuation"
    assert settled["events"][0]["event_name"] == "ValuationCommitted"

    # The commitment can be recomputed from the stored estimate, and its value does not appear on-chain.
    from app.blockchain import hashing

    salt = db.scalar(select(BlockchainRecord)).salt
    from decimal import Decimal

    expected = hashing.valuation_commitment(valuation["id"], Decimal(valuation["predicted_value"]), valuation["model_version"], salt)
    assert settled["events"][0]["args"]["valuationHash"] == expected
    calldata = bytes(chain.eth.get_transaction(settled["tx_hash"])["input"])
    assert str(int(Decimal(valuation["predicted_value"]))).encode() not in calldata
    # The property record itself is untouched by committing an estimate.
    assert owner.post(f"/api/v1/blockchain/properties/{prop['id']}/verify").json()["on_chain_version"] == 1


def test_a_request_can_be_cancelled_by_either_party_and_unblocks_the_property(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    url = "/api/v1/blockchain/ownership-transfer"
    first = buyer.post(url, json={"property_id": prop["id"]}).json()
    assert make_actor().post(f"{url}/{first['id']}/cancel").status_code == 404
    cancelled = buyer.post(f"{url}/{first['id']}/cancel").json()
    assert cancelled["transfer"]["status"] == "cancelled" and cancelled["call"] is None
    assert buyer.post(f"{url}/{first['id']}/cancel").status_code == 409

    second = buyer.post(url, json={"property_id": prop["id"]})
    assert second.status_code == 201
    assert owner.post(f"{url}/{second.json()['id']}/cancel").json()["call"] is None


def test_a_live_proposal_is_cancelled_on_chain_by_the_controller(chain, make_actor, make_property):
    owner, buyer, owner_wallet, buyer_wallet, prop = _setup_transfer(chain, make_actor, make_property)
    transfer = _propose(chain, owner, owner_wallet, prop, buyer)
    url = f"/api/v1/blockchain/ownership-transfer/{transfer['id']}"
    assert buyer.post(f"{url}/cancel").status_code == 403

    call = owner.post(f"{url}/cancel").json()["call"]
    # Nothing changes until the cancellation is confirmed on-chain.
    assert owner.get("/api/v1/blockchain/ownership-transfer").json()[0]["status"] == "proposed"
    tx_hash = _send_from_wallet(chain, owner_wallet, call["to"], call["data"])
    assert owner.post(f"/api/v1/blockchain/transactions/{call['transaction_id']}/submit", json={"tx_hash": tx_hash}).status_code == 200
    assert _settle(owner, call["transaction_id"])["events"][0]["event_name"] == "TransferCancelled"
    assert owner.get("/api/v1/blockchain/ownership-transfer").json()[0]["status"] == "cancelled"
    assert buyer.post(f"{url}/accept").status_code == 409
