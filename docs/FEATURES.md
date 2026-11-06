# Features

What PropTwin AI does, who can use each feature, and where its limits are.

All bundled data is fictional, and the bundled model is trained on it. Figures from a default install show how the product works. They say nothing about real property.

## Who can use what

| Feature | Guest | Owner | Investor | Verifier | Admin |
|---|---|---|---|---|---|
| Browse, search and compare listings | Yes | Yes | Yes | Yes | Yes |
| Market insights | Yes | Yes | Yes | Yes | Yes |
| Investment calculator | Yes | Yes | Yes | Yes | Yes |
| Decision snapshot and property report (public listings) | Yes | Yes | Yes | Yes | Yes |
| Help center | Yes | Yes | Yes | Yes | Yes |
| AI valuation and valuation history | | Yes | Yes | Yes | Yes |
| Save listings | | Yes | Yes | Yes | Yes |
| Scenario simulator | | Yes | Yes | | Yes |
| Register properties, portfolio view, digital twins | | Yes | | | Yes |
| Request verification, commit to the blockchain | | Yes | | | Yes |
| Decide verification requests | | | | Yes | Yes |
| Manage users and models, monitoring, audit log | | | | | Yes |

## New-user experience

| Feature | What it does | Where |
|---|---|---|
| One-command start | `.\start.ps1` creates secrets, starts every service, loads demo data, and activates a model. It is safe to run again. | Repository root |
| One-click demo accounts | Four ready-filled accounts open without a password. Off unless `DEMO_LOGIN_ENABLED` is true, and the API refuses to start with it on in production. | Home and sign-in pages |
| Getting-started checklist | Steps for your role. Each one ticks only when its real record exists, and links to the next thing to do. | Dashboard |
| Page guides | Three short steps at the top of each tool page. Hiding one is remembered in that browser. | Tool pages |
| Term explanations | A help icon beside technical terms explains them in a sentence. | Snapshot, calculator, market pages |
| Help center | Step-by-step guides by role, a searchable glossary, and common questions. | `/help` |

## Decisions and information

### Decision snapshot

Answers two questions on each property's page: is this price reasonable, and how far can the record be trusted?

- **Asking price check:** shows the price against the AI estimate's range, as below, inside or above.
- **Price per square foot:** against the locality median.
- **Gross rental yield:** against the locality's yield.
- **Locality movement:** the 12-month change in its price index.
- **What stands out:** plain sentences built from the comparisons above.

*Limits:* this is arithmetic on stored figures. It never recommends buying or selling. An estimate counts as out of date only when an input it used has changed.

### Market insights

Ranks localities by price per square foot, 12-month change, 5-year growth per year, and gross yield, with a filter by city. Any locality's price index can be charted, and compared with a second one.

*Limits:* reads the `market_observations` table, which holds fictional data by default. To use real data, load a licensed source with `is_synthetic` set to false.

### Investment calculator

From a price, loan terms, rent, vacancy, costs and an assumed yearly value change, it works out:

- monthly instalment, monthly cash flow and break-even rent
- gross yield, cap rate, cash-on-cash return and debt coverage
- cash needed upfront, total interest, and projected equity by year

A property's asking price and rent can be filled in automatically with **Calculate returns**.

*Limits:* a hypothetical calculation. It leaves out income tax, rent growth, major repairs and the cost of selling. The starting rate, costs and growth are examples to replace, not quotes.

### Comparison

Up to four listings side by side, including price per square foot and gross yield. The lowest price per square foot and the highest yield are highlighted.

### Property report

A one-page summary of the estimate, price check, comparisons and trust status, to print or save as a PDF. It contains only what the viewer may already see.

### Portfolio view

For owners: total AI-estimated value, annual rent on record, and how many properties are verified and on-chain. Each property shows its single next step.

*Limits:* covers the newest 200 properties, and says so if there are more. Totals appear only when all properties use one currency.

## Core services

| Service | What you get | What it is not |
|---|---|---|
| **AI valuation** | A value, a 90% range, what moved the number, and stated limits | A sale price or a certified appraisal |
| **Digital twin** | A software copy of the record that keeps every past state | A live feed: it has no sensors |
| **Scenario simulator** | Market, renovation, rent and maintenance what-ifs, compared side by side, with the method shown | A forecast |
| **Verification** | A named verifier's recorded decision on the submitted documents | A legal title search |
| **Blockchain record** | A salted hash on-chain, and a check that names any fields changed since | Proof of legal ownership, or that the data was true |
| **Ownership transfer** | A two-step, wallet-signed change of control of the on-chain record | A legal transfer of property |

## Before using this with real people

The app runs and is ready to explore locally, with fictional data. Using it for real decisions also needs:

1. **Real data:** a licensed sales dataset to retrain the model, and a licensed market data source.
2. **Hosting:** a production deployment with HTTPS. This has not been run. See [Deployment](DEPLOYMENT.md).
3. **Email:** an SMTP provider for password resets and verification emails.
4. **A real network:** a public blockchain network and a funded relayer key. Chains here are local.
5. **Review:** an independent security review, a contract audit, and legal advice on how results are described.
