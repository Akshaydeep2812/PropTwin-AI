# Implementation plan

Status records only what has actually been run. Test figures are in [TESTING.md](TESTING.md).

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, schema, API contract | Done |
| 2 | Foundation: config, schema, migrations on MySQL, Docker, seed data | Done |
| 3 | Authentication, roles, properties, verification | Done |
| 4 | ML pipeline and valuation API | Done, on synthetic data |
| 5 | Digital twin and simulation | Done |
| 6 | Contract, Web3 integration, verification | Done, on a local chain |
| 7 | All 18 frontend pages | Done |
| 8 | End-to-end integration | Done |
| 9 | Deployment | **Partly done.** The Compose stack is verified from a clean copy. Cloud deployment is documented but not run |
| 10 | Handover documentation | Done |

## Definition of done

| Criterion | Status |
|---|---|
| Runs locally from documented instructions | Met: the Docker path was followed from a clean copy. The non-Docker path was used during development, but not rerun from clean |
| Register and log in | Met |
| Create and manage property records | Met |
| Train, evaluate and load a PyTorch model | Met |
| Real predictions when a model is available | Met |
| Valuation history saved and displayed | Met |
| Create and update digital twins | Met |
| Reproducible simulations | Met |
| Contracts compile and pass tests | Met |
| Submit and verify transactions on a local network | Met |
| Check record hashes | Met |
| Reject unauthorized operations | Met |
| Frontend shows real backend data | Met |
| Automated tests cover critical workflows | Met |
| Deployment and maintenance documentation | Met. Cloud steps are unverified, and say so |

## Inputs needed from the project owner

None of these block local use.

- Hosting accounts for the frontend, backend and managed MySQL.
- A testnet RPC URL and a funded test wallet, for a public testnet demo.
- A licensed real-estate dataset, for real valuation. Until then, all metrics describe synthetic data.
- SMTP credentials, for live email.

## Future improvements

- Collect actual sale outcomes, so that model accuracy can be monitored, not only drift.
- Object storage for uploads, and a shared store for rate limits, to allow several API processes.
- Multi-factor authentication, and assigning verifiers to specific requests.
- Continuous integration running every suite on each push.
- Code-split the frontend: the bundle is 838 kB, mostly the charting library.
- A contract audit before any use on a network holding real value.
