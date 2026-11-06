# Blockchain guide

## What this does and does not prove

A confirmed record proves that a specific hash was committed at a specific time, and that the current off-chain record does or does not still match it.

It does **not** prove that the data was true when committed, that documents are authentic, or that anyone legally owns the property. A wallet address that controls a record is not a legal owner.

## Contract: `PropertyRegistry`

| Function | Caller | Purpose |
|---|---|---|
| `register(key, hash, controller)` | Registrar | Create a record once. Duplicates revert |
| `updateRecord(key, hash, expectedVersion)` | Registrar or controller | Commit a new hash. A stale version reverts |
| `commitValuation(key, hash)` | Registrar or controller | Emit a commitment to one estimate |
| `assignController(key, newController)` | Registrar | Hand a registrar-held record to a user's wallet. It cannot take one back |
| `proposeTransfer(key, to)` | Controller | First step of a transfer. Nothing moves yet |
| `cancelTransfer(key)` | Controller | Withdraw a proposal |
| `acceptTransfer(key)` | Proposed recipient | Second step. Control moves |
| `pause()`, `unpause()` | Pauser | Stop or resume all state changes |

**Authorization:** the deployer holds `DEFAULT_ADMIN_ROLE` and `PAUSER_ROLE`. The relayer holds `REGISTRAR_ROLE`. Keep the admin key offline on any public network, and pass `REGISTRAR_ADDRESS` when deploying.

## What goes on-chain

Only a `keccak256` property key, the record hash, a version number, a controller address, timestamps and events. Never an address, name, document, or price. A test inspects real transaction data to confirm this.

## Record hashing

`hash = keccak256(salt || canonical_json)`. The code is in `backend/app/blockchain/hashing.py`.

**Covered fields (hash version 1):** `property_id`, `property_type`, `address_line1`, `locality`, `city`, `state`, `postal_code`, `latitude`, `longitude`, `built_up_area_sqft`, `land_area_sqft`, `bedrooms`, `bathrooms`, `construction_year`, `floor_number`, `total_floors`, `condition`, `amenities`, `parking_spaces`, `last_sale_price`, `last_sale_date`, plus `hash_version`.

**Not covered, on purpose:** title and description (marketing text), asking price and rent (offers, not facts), listing and verification status (workflow state), and owner (changes through a transfer and is tracked by the controller).

**Normalization:** keys are sorted, text is NFC-normalized with collapsed whitespace, decimals are written in canonical form (`1200` and `1200.00` match), and amenities are lowercased and sorted. Floats are refused because their text form is unstable.

**Why a salt:** property details are guessable. Without a salt, anyone could hash candidate addresses and compare them with the public value. Each record has its own 32-byte salt, kept off-chain. The cost is that outside parties cannot verify a hash without being given the salt and the record.

To change the covered fields or the normalization, add a new `HASH_VERSION`. Otherwise every stored commitment becomes uncheckable, and `test_known_answer_pins_the_algorithm` will fail to warn you.

## Signing

| Path | Used for | Who signs |
|---|---|---|
| Relayer | Register, update, commit estimate, hand over control | The server, using `BLOCKCHAIN_RELAYER_PRIVATE_KEY` |
| Wallet | Propose, accept, cancel a transfer | The user's browser wallet |

For a wallet transaction, the API prepares the call, the browser wallet signs and sends it, and the client hands back the hash. **The hash is not trusted:** the API reads the transaction from the chain and checks its sender, contract and call data against what it prepared.

## Transaction lifecycle

`pending` (prepared), `submitted` (on the network), then `confirmed`, `failed`, or `reverted`.

`confirmed` is set in one place only, `refresh_transaction`, and only from a successful receipt with at least `BLOCKCHAIN_CONFIRMATIONS` blocks. The background worker reconciles open transactions, so a status settles even if the user closes the page. A transaction the network no longer knows after 30 minutes is marked `failed`.

## Ownership transfer

1. The owner names a recipient, or an investor requests a listed property.
2. The owner's wallet signs the proposal. Nothing moves.
3. The recipient's wallet signs the acceptance.
4. When that is confirmed, the on-chain controller, the application's owner and the ownership history all change together.

Both people must have linked a wallet by signing a single-use challenge. A record registered before its owner linked a wallet must first be moved with **Move control to my wallet**. A request can be cancelled by either person. A live proposal must be cancelled on-chain by its controller.

**This does not transfer legal title,** which requires your jurisdiction's legal process. The interface says so at each step.

## Local network

```powershell
cd blockchain
npm install
npm test                     # contract tests
npm run node                 # leave running in its own terminal
npm run deploy:local         # in a second terminal
cd ..
python scripts/configure_local_chain.py
```

A standalone node mines reverting transactions as failed receipts, as real networks do. It loses all state when it stops, and earlier records then report `missing_on_chain`. Redeploy, and register them again.

## Public testnet

This path has not been run, because it needs an RPC URL and a funded wallet.

```powershell
$env:TESTNET_RPC_URL = "<your RPC URL>"
$env:TESTNET_DEPLOYER_PRIVATE_KEY = "<admin key, not used by the server>"
$env:REGISTRAR_ADDRESS = "<address of a separate relayer key>"
cd blockchain
npx hardhat run scripts/deploy.ts --network testnet
```

Then set these on the backend. Use at least 3 confirmations.

```text
BLOCKCHAIN_RPC_URL, BLOCKCHAIN_NETWORK_NAME, BLOCKCHAIN_CHAIN_ID, BLOCKCHAIN_CONTRACT_ADDRESS,
BLOCKCHAIN_RELAYER_PRIVATE_KEY, BLOCKCHAIN_CONFIRMATIONS
```

Copy `blockchain/abi/PropertyRegistry.json` to the backend host. Fund the relayer with test currency, and watch its balance: failed sends are recorded with the reason.

The contract has not had an independent security audit. It must have one before use on any network holding real value.
