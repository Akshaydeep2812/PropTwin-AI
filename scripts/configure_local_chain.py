"""Points .env at a local Hardhat node after `npm run deploy:local`. Usage: python scripts/configure_local_chain.py

The relayer key is derived from Hardhat's public test mnemonic. It is worthless outside a local node, and the API
refuses to start with it when APP_ENV=production. Never use this script for a testnet or production deployment.
"""

import json
import sys
from pathlib import Path

from eth_account import Account

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
DEPLOYMENT = REPO_ROOT / "blockchain" / "deployments" / "localhost.json"
HARDHAT_TEST_MNEMONIC = "test test test test test test test test test test test junk"
RELAYER_INDEX = 1


def main() -> int:
    if not ENV_FILE.is_file():
        print("Create .env first: Copy-Item .env.example .env", file=sys.stderr)
        return 1
    if not DEPLOYMENT.is_file():
        print("No local deployment found. Run: npm run deploy:local (in blockchain/)", file=sys.stderr)
        return 1
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    if any(line.strip().lower() == "app_env=production" for line in lines):
        print("Refusing to write development chain settings into a production .env.", file=sys.stderr)
        return 1

    deployment = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
    Account.enable_unaudited_hdwallet_features()
    relayer = Account.from_mnemonic(HARDHAT_TEST_MNEMONIC, account_path=f"m/44'/60'/0'/0/{RELAYER_INDEX}")
    if relayer.address != deployment["registrar"]:
        print("The deployment's registrar is not the local relayer. Was this deployed by deploy:local?", file=sys.stderr)
        return 1

    updates = {
        "BLOCKCHAIN_RPC_URL": "http://127.0.0.1:8545",
        "BLOCKCHAIN_NETWORK_NAME": "hardhat-local",
        "BLOCKCHAIN_CHAIN_ID": str(deployment["chainId"]),
        "BLOCKCHAIN_CONTRACT_ADDRESS": deployment["address"],
        "BLOCKCHAIN_RELAYER_PRIVATE_KEY": relayer.key.to_0x_hex(),
        "BLOCKCHAIN_CONFIRMATIONS": "1",
    }
    kept = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    ENV_FILE.write_text("\n".join(kept + [f"{key}={value}" for key, value in updates.items()]) + "\n", encoding="utf-8")
    print(f"Updated .env for contract {deployment['address']} on chain {deployment['chainId']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
