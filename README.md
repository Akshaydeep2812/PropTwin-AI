# PropTwin AI

A real estate analytics platform combining three technologies:

- **Machine-learning valuation:** a PyTorch model estimates market value, with a range and its limits.
- **Digital twin:** a software copy of each property keeps every past state and tests what-if scenarios.
- **Blockchain records:** salted hashes on an Ethereum-compatible network make later changes to a record detectable.

Owners can value a property, test what-if scenarios, and keep a verified record. Buyers and investors can check an asking price, compare localities, and work out returns. See [Features](docs/FEATURES.md) for exactly what each feature does and who can use it.

The product keeps four kinds of claim separate, and labels each everywhere it appears:

| Label | Means | Does not mean |
|---|---|---|
| AI estimate | A model's output from the inputs shown | A sale price or certified appraisal |
| Hypothetical simulation | The stated formula applied to the stated assumptions | A forecast |
| Verifier decision | A named person reviewed the files | A legal title search |
| Blockchain-confirmed | A transaction met the confirmation policy | Legal ownership, or that the data is true |

> **All bundled data is synthetic.** The included model is trained on fictional data. Its metrics show that the pipeline works. They say nothing about valuing real property. To value real property, train on a licensed dataset (see [ML pipeline](docs/ML_PIPELINE.md)).

## Before you start

Keep this project **outside OneDrive** or any other synced folder. OneDrive can turn files into cloud placeholders, which test tools skip without warning, and it slows installs considerably.

## Quick start

Requires Docker Desktop. In PowerShell, from the repository root:

```powershell
.\start.ps1
```

If Windows blocks the script, run `powershell -ExecutionPolicy Bypass -File .\start.ps1` instead.

This creates `.env` with new random secrets, starts every service, loads demo data, activates a valuation model, and opens <http://localhost:5173>. It is safe to run again. The first run downloads PyTorch and takes several minutes. API docs are at <http://localhost:8000/docs>. To stop everything, run `docker compose stop`.

On the home page, choose an **Explore as** button to open a ready-filled demo account without a password:

| Demo account | Role |
|---|---|
| `demo.owner@proptwin.example` | Property owner |
| `demo.investor@proptwin.example` | Buyer or investor |
| `demo.verifier@proptwin.example` | Property verifier |
| `demo.admin@proptwin.example` | Administrator and owner |

To sign in with a password instead, use `DEMO_PASSWORD` from `.env`. Demo accounts and one-click sign-in are refused when `APP_ENV=production`.

To run without Docker, follow [the deployment guide](docs/DEPLOYMENT.md).

## Repository layout

| Path | Contents |
|---|---|
| `frontend/` | React, Vite, Tailwind client and its tests |
| `backend/` | FastAPI service, migrations and tests |
| `ml/` | Dataset generator, training pipeline and model artifacts |
| `blockchain/` | `PropertyRegistry` contract, deployment script and tests |
| `database/` | Demo data and database setup |
| `scripts/` | Local chain configuration and container startup |
| `docs/` | The documents below |

## Documentation

- [Features](docs/FEATURES.md): what each feature does, who can use it, and its limits
- [Architecture](docs/ARCHITECTURE.md): design and key decisions
- [Database schema](docs/DATABASE_SCHEMA.md): ER diagram, tables and retention
- [API](docs/API_DOCUMENTATION.md): endpoints and sample requests
- [ML pipeline](docs/ML_PIPELINE.md): data, training, metrics and promotion
- [Blockchain guide](docs/BLOCKCHAIN_GUIDE.md): contract, hashing, signing and limits
- [Deployment](docs/DEPLOYMENT.md): Windows setup and cloud deployment
- [Maintenance](docs/MAINTENANCE.md): backups, retraining, monitoring and troubleshooting
- [Security](docs/SECURITY.md): controls and known trade-offs
- [Testing](docs/TESTING.md): how to run each suite, with recorded results

## Known limitations

- The model has never seen real data. Its accuracy on real property is unknown.
- Valuation factors describe the model's sensitivity, not market causes.
- The digital twin is software only, with no sensors and no real-time feed.
- A record's salt is held by the application, so outside parties cannot check a hash unless it is disclosed to them.
- A local Hardhat chain is reset when it restarts. Earlier records then show as missing on-chain.
- Files are stored on local disk. A multi-server deployment needs an object storage adapter.
- Rate limits are counted per process. Running several API processes needs a shared store.
- Cloud deployment and public testnet use have not been run, because they need accounts this project does not hold.
