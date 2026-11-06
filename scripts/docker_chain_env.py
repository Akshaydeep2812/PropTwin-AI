"""Prints shell exports for the local Compose chain. Used only by docker-entrypoint.sh when USE_HARDHAT_DEV_RELAYER=true.

The key comes from Hardhat's public test mnemonic, so it protects nothing and exists only on the throwaway local node.
"""

import json
import os
import sys
from pathlib import Path

from eth_account import Account

DEPLOYMENT = Path("/app/blockchain/deployments/localhost.json")
HARDHAT_TEST_MNEMONIC = "test test test test test test test test test test test junk"


def main() -> int:
    if os.environ.get("APP_ENV", "").lower() == "production":
        print("USE_HARDHAT_DEV_RELAYER cannot be used in production.", file=sys.stderr)
        return 1
    deployment = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
    Account.enable_unaudited_hdwallet_features()
    relayer = Account.from_mnemonic(HARDHAT_TEST_MNEMONIC, account_path="m/44'/60'/0'/0/1")
    print(f"export BLOCKCHAIN_CONTRACT_ADDRESS={deployment['address']}")
    print(f"export BLOCKCHAIN_RELAYER_PRIVATE_KEY={relayer.key.to_0x_hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
