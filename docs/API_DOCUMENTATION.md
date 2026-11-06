# API specification

Base path `/api/v1`. Interactive OpenAPI docs at `/docs`. JSON bodies; ISO 8601 UTC timestamps; money as decimal strings. Protected routes take `Authorization: Bearer <access token>`.

## Conventions

**Errors**

```json
{ "error": { "code": "property_not_found", "message": "Property not found.", "request_id": "..." } }
```

`401` unauthenticated, `403` wrong role, `404` absent or not visible to the caller, `409` conflict, `422` validation, `429` rate limited, `503` dependency unavailable (for example `model_unavailable`).

**Pagination**: `?page=1&page_size=20` returns `{ "items": [], "page": 1, "page_size": 20, "total": 0 }`. Maximum page size 100.

## Endpoints

Access: **P** public, **U** any signed-in user, **O** owner of the object or admin, **I** investor, **V** verifier, **A** admin.

### Health

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health/live` | P | Process is up |
| GET | `/health/ready` | P | Database reachable; reports model and chain status |

### Authentication and users

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/auth/register` | P | Create an `owner` or `investor` account |
| POST | `/auth/login` | P | Rate limited; sets refresh cookie |
| POST | `/auth/refresh` | cookie | Rotates the refresh token |
| POST | `/auth/logout` | cookie | Revokes the session |
| POST | `/auth/logout-all` | U | Revokes all sessions |
| GET | `/auth/me` | U | Current user with roles |
| POST | `/auth/password-reset/request`, `/auth/password-reset/confirm` | P | Reset; the response does not reveal whether an email exists |
| POST | `/auth/email-verification/request`, `/auth/email-verification/confirm` | U, P | Verify email |
| PATCH | `/users/me` | U | Update profile |
| POST | `/users/me/password` | U | Change password; revokes other sessions |
| POST | `/users/me/wallet/challenge`, `/users/me/wallet` | U | Link a wallet by signing a nonce |

### Properties

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/properties` | P | Listed properties; filter by city, type, price, size; sort; paginate. No street address or owner data |
| GET | `/properties/mine` | U | The caller's properties |
| POST | `/properties` | owner role | Create |
| GET | `/properties/compare?ids=` | P | Compare listed properties, up to 4 |
| GET | `/properties/{id}` | P / O | Public view if listed; full view for owner or admin |
| PATCH, DELETE | `/properties/{id}` | O | Update (syncs twin); archive |
| POST | `/properties/{id}/images` | O | Upload image |
| GET | `/properties/{id}/images/{image_id}` | P if listed | Fetch image |
| POST | `/properties/{id}/documents` | O | Upload private document |
| GET | `/properties/{id}/documents` | O, V | List |
| GET | `/properties/{id}/documents/{document_id}` | O, V | Download |
| POST | `/properties/{id}/renovations` | O | Add renovation |
| POST | `/properties/{id}/report` | U | Report a listing |
| GET, PUT, DELETE | `/saved-properties`, `/saved-properties/{id}` | U | Favorites |

### Verification

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/properties/{id}/verification-requests` | O | Submit |
| GET | `/properties/{id}/verification-requests` | O, V | History |
| GET | `/verification/queue` | V, A | Open requests |
| POST | `/verification/{request_id}/decision` | V, A | Approve or reject with notes. A verifier cannot decide on their own property |

### Valuations

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/valuations/predict` | U | Value by `property_id` (O) or by inline features |
| POST | `/valuations/batch` | U | Up to 50 items |
| GET | `/valuations/{id}` | requester, O | One estimate |
| GET | `/properties/{id}/valuations` | P if listed (limited), O (full) | History |
| GET | `/admin/models` | A | Registry |
| GET | `/admin/models/{version}/metrics` | A | Stored evaluation metrics |
| POST | `/admin/models/{version}/promote` | A | Approve or activate; refuses if the model failed the baseline gate |

Response shape (values illustrative):

```json
{
  "id": "...", "property_id": "...",
  "predicted_value": "8450000.00", "currency": "INR",
  "interval": { "lower": "7200000.00", "upper": "9900000.00", "nominal_coverage": 0.9, "method": "split_conformal" },
  "predicted_at": "2026-11-05T15:00:00Z", "model_version": "...",
  "input_summary": {}, "factors": [ { "feature": "built_up_area_sqft", "effect": "2100000.00", "reference": "median" } ],
  "historical_comparison": { "previous_value": null, "last_sale_price": "7000000.00" },
  "trained_on_synthetic_data": true,
  "limitations": ["..."],
  "disclaimer": "Estimated market value. Not a guaranteed sale price or certified appraisal."
}
```

### Digital twins

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/properties/{id}/twin` | O | Create from the property record |
| GET | `/properties/{id}/twin` | O, or I if listed | Current state |
| PATCH | `/twins/{id}` | O | Update maintenance, rent, or market inputs; writes a snapshot |
| POST | `/twins/{id}/simulate` | O, I if listed | Run a scenario |
| GET | `/twins/{id}/history` | O | Snapshots |
| GET | `/twins/{id}/simulations` | O; I sees own | Simulation history |

Simulation request:

```json
{ "name": "Market down 10%", "market_change_pct": "-10", "renovation_value_uplift_pct": "0",
  "renovation_cost": "0", "condition_after": null, "monthly_rent_change_pct": "5", "annual_maintenance_cost": "60000" }
```

### Blockchain

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/blockchain/properties/{id}/register` | O | Commit the record, or commit an update if already registered |
| POST | `/blockchain/properties/{id}/verify` | O, V, A | Recompute the hash and compare it to the chain |
| GET | `/blockchain/properties/{id}/history` | O, V, A | Transactions and events |
| GET | `/blockchain/transactions/{id}` | initiator, O, A | Status; refreshes from the receipt |
| POST | `/blockchain/transactions/{id}/submit` | initiator | Hand in a wallet-signed hash; checked against the chain |
| POST | `/blockchain/transactions/{id}/abandon` | initiator | Discard a prepared wallet call that was never sent |
| POST | `/blockchain/properties/{id}/assign-controller` | O | Move a relayer-held record to the owner's linked wallet |
| GET | `/blockchain/properties/{id}/record` | P if listed | Public record, without the salt or committed payload |
| POST | `/blockchain/valuations/{id}/commit` | O | Commit a salted hash of one estimate on-chain |
| GET | `/blockchain/ownership-transfer` | U | The caller's transfers |
| POST | `/blockchain/ownership-transfer` | O or I | Create a transfer: an owner names a recipient, an investor requests a listing |
| POST | `/blockchain/ownership-transfer/{id}/propose` | current owner | Returns unsigned call data for the proposal |
| POST | `/blockchain/ownership-transfer/{id}/accept` | proposed recipient | Returns unsigned call data for acceptance |
| POST | `/blockchain/ownership-transfer/{id}/cancel` | either party | Closes a request directly. A live proposal returns call data for its controller to sign |
| GET | `/blockchain/network` | P | Network, contract address, reachability |

`register` returns `202`, not success: the client watches the transaction until it is `confirmed`, `failed` or `reverted`.

### Dashboards, notifications, administration

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/dashboard` | U | Role-aware summary |
| GET, POST | `/notifications`, `/notifications/{id}/read` | U | Notifications |
| GET, PATCH | `/admin/users`, `/admin/users/{id}` | A | List, deactivate, assign roles. Admins cannot change their own roles |
| GET | `/admin/audit-logs` | A | Audit trail |
| GET | `/admin/transactions` | A | Chain monitoring |
| GET, PATCH | `/admin/reports`, `/admin/reports/{id}` | A | Reported listings |
| GET | `/admin/monitoring` | A | Prediction distribution and drift, job status |

Twins also expose `GET /twins/{id}/market`, the locality's index series, for the same viewers as the twin.

## Sample requests

Replace `$api` and `$token`. Passwords and tokens below are placeholders.

```powershell
$api = "http://localhost:8000/api/v1"

# Sign in. The refresh token arrives as an HttpOnly cookie; the access token is in the body.
$session = Invoke-RestMethod -Method Post "$api/auth/login" -ContentType "application/json" `
  -Body '{"email":"demo.owner@proptwin.example","password":"<your DEMO_PASSWORD>"}'
$headers = @{ Authorization = "Bearer $($session.access_token)" }

# Value a property that is not registered.
Invoke-RestMethod -Method Post "$api/valuations/predict" -Headers $headers -ContentType "application/json" `
  -Body '{"features":{"property_type":"apartment","built_up_area_sqft":"1200","locality":"Riverside","city":"Sample City","condition":"good","bedrooms":2,"bathrooms":2,"construction_year":2015}}'

# Run a scenario. Replace <twin_id>.
Invoke-RestMethod -Method Post "$api/twins/<twin_id>/simulate" -Headers $headers -ContentType "application/json" `
  -Body '{"name":"Market down 10%","market_change_pct":"-10"}'

# Commit to the chain, then watch the transaction until it settles. Replace <property_id>.
$tx = Invoke-RestMethod -Method Post "$api/blockchain/properties/<property_id>/register" -Headers $headers
Invoke-RestMethod "$api/blockchain/transactions/$($tx.id)" -Headers $headers

# Check a record against the chain.
Invoke-RestMethod -Method Post "$api/blockchain/properties/<property_id>/verify" -Headers $headers
```

Every error has this shape, with `fields` added for validation errors:

```json
{ "error": { "code": "model_unavailable", "message": "No approved valuation model is active. No estimate has been produced.", "request_id": "..." } }
```

## Insights and onboarding

| Method and path | Access | Purpose |
|---|---|---|
| `GET /market/localities` | P | Each locality's latest median price, rent, gross yield, 12-month change, 5-year growth and listing count |
| `GET /market/localities/{locality}/trend` | P | That locality's monthly index and price per square foot |
| `GET /properties/{id}/insights` | P, or whoever can see the property | Asking price against the estimate and locality, status, and plain-language takeaways. `completeness` is set only for the owner or an admin |
| `GET /properties/mine/portfolio` | U | The caller's properties, up to 200, each with its next step, plus totals |
| `GET /auth/demo-accounts` | P | Demo accounts available for one-click sign-in. Empty unless `DEMO_LOGIN_ENABLED` is true |
| `POST /auth/demo-login` | P | Opens a session for a demo account. Answers `404` for any other account, or when switched off |

`GET /dashboard` also returns `onboarding`, the caller's checklist with each step's `done` state. `GET /verification/queue` items also include `property_title`.
