"""The only module that talks to the chain. It knows nothing about the database or the application's rules."""

import json
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any

from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.exceptions import TransactionNotFound

from app.core.config import Settings, get_settings

RPC_TIMEOUT_SECONDS = 10
GAS_SAFETY_MARGIN = 1.3


class ChainUnavailable(RuntimeError):
    """The node cannot be reached or the integration is not configured."""


class ChainRejected(RuntimeError):
    """The node refused the transaction, for example because it would revert."""


@dataclass(frozen=True)
class ChainTransaction:
    sender: str
    to: str | None
    data: str


@dataclass(frozen=True)
class ChainReceipt:
    succeeded: bool
    block_number: int
    logs: list[Any]


@dataclass(frozen=True)
class OnChainRecord:
    record_hash: str
    controller: str
    version: int
    updated_at: int


class ChainGateway:
    def __init__(self, settings: Settings):
        if not settings.blockchain_rpc_url or not settings.blockchain_contract_address:
            raise ChainUnavailable("Blockchain integration is not configured.")
        if not settings.blockchain_abi_path.is_file():
            raise ChainUnavailable("Contract ABI not found. Deploy the contract first.")
        self.settings = settings
        self.web3 = Web3(HTTPProvider(settings.blockchain_rpc_url, request_kwargs={"timeout": RPC_TIMEOUT_SECONDS}))
        self.contract_address = Web3.to_checksum_address(settings.blockchain_contract_address)
        self.contract = self.web3.eth.contract(address=self.contract_address, abi=json.loads(settings.blockchain_abi_path.read_text(encoding="utf-8")))
        self._nonce_lock = Lock()

    @property
    def network(self) -> str:
        return self.settings.blockchain_network_name

    @property
    def relayer_address(self) -> str | None:
        key = self.settings.blockchain_relayer_private_key
        return None if key is None else Account.from_key(key.get_secret_value()).address

    def _guard(self, operation):
        try:
            return operation()
        except (TransactionNotFound, ChainRejected):
            raise
        except Exception as exc:
            if _is_connection_error(exc):
                raise ChainUnavailable(f"The blockchain node is unreachable: {type(exc).__name__}") from exc
            raise

    def is_reachable(self) -> bool:
        try:
            return bool(self.web3.is_connected()) and self.web3.eth.chain_id == self.settings.blockchain_chain_id
        except Exception:
            return False

    def encode_call(self, function: str, *args: Any) -> str:
        return self.contract.encode_abi(function, args=list(args))

    def send_as_relayer(self, call_data: str) -> str:
        """Signs with the server's key. The lock keeps nonces in order when requests arrive together."""
        key = self.settings.blockchain_relayer_private_key
        if key is None:
            raise ChainUnavailable("No relayer key is configured.")
        account = Account.from_key(key.get_secret_value())

        def send() -> str:
            with self._nonce_lock:
                transaction = {
                    "from": account.address,
                    "to": self.contract_address,
                    "data": call_data,
                    "chainId": self.settings.blockchain_chain_id,
                    "nonce": self.web3.eth.get_transaction_count(account.address, "pending"),
                }
                try:
                    transaction["gas"] = int(self.web3.eth.estimate_gas(transaction) * GAS_SAFETY_MARGIN)
                except Exception as exc:
                    if _is_connection_error(exc):
                        raise
                    raise ChainRejected(_short_reason(exc)) from exc
                latest = self.web3.eth.get_block("latest")
                priority = self.web3.to_wei(1, "gwei")
                transaction["maxPriorityFeePerGas"] = priority
                transaction["maxFeePerGas"] = latest.get("baseFeePerGas", 0) * 2 + priority
                signed = account.sign_transaction(transaction)
                return self.web3.eth.send_raw_transaction(signed.raw_transaction).to_0x_hex()

        return self._guard(send)

    def get_transaction(self, tx_hash: str) -> ChainTransaction | None:
        def read() -> ChainTransaction | None:
            try:
                transaction = self.web3.eth.get_transaction(tx_hash)
            except TransactionNotFound:
                return None
            return ChainTransaction(transaction["from"], transaction.get("to"), Web3.to_hex(transaction["input"]))

        return self._guard(read)

    def get_receipt(self, tx_hash: str) -> ChainReceipt | None:
        def read() -> ChainReceipt | None:
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                return None
            return ChainReceipt(receipt["status"] == 1, receipt["blockNumber"], list(receipt["logs"]))

        return self._guard(read)

    def latest_block(self) -> int:
        return self._guard(lambda: self.web3.eth.block_number)

    def get_record(self, key: str) -> OnChainRecord | None:
        def read() -> OnChainRecord | None:
            record = self.contract.functions.getRecord(key).call()
            if record[2] == 0:
                return None
            return OnChainRecord(Web3.to_hex(record[0]), record[1], int(record[2]), int(record[3]))

        return self._guard(read)

    def pending_controller(self, key: str) -> str | None:
        def read() -> str | None:
            value = self.contract.functions.pendingController(key).call()
            return None if int(value, 16) == 0 else value

        return self._guard(read)

    def decode_events(self, receipt: ChainReceipt) -> list[dict[str, Any]]:
        """Only logs emitted by this contract count. Any other contract can emit look-alike events."""
        decoded = []
        for log in receipt.logs:
            if Web3.to_checksum_address(log["address"]) != self.contract_address:
                continue
            for event in self.contract.events:
                try:
                    parsed = event().process_log(log)
                except Exception:
                    continue
                decoded.append(
                    {
                        "name": parsed["event"],
                        "log_index": parsed["logIndex"],
                        "block_number": parsed["blockNumber"],
                        "args": {name: (Web3.to_hex(value) if isinstance(value, (bytes, bytearray)) else value) for name, value in parsed["args"].items()},
                    }
                )
                break
        return decoded


def _is_connection_error(exc: Exception) -> bool:
    # A JSON-RPC error means the node answered and refused, so it is deliberately not a connection failure.
    names = {klass.__name__ for klass in type(exc).__mro__}
    return bool(names & {"ConnectionError", "Timeout", "ConnectTimeout", "ReadTimeout", "RemoteDisconnected", "ProviderConnectionError"})


def _short_reason(exc: Exception) -> str:
    return str(exc)[:300]


@lru_cache
def _cached_gateway(url: str | None, address: str | None) -> ChainGateway:
    return ChainGateway(get_settings())


def get_gateway() -> ChainGateway:
    settings = get_settings()
    return _cached_gateway(settings.blockchain_rpc_url, settings.blockchain_contract_address)
