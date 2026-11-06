# Maintenance

## Routine tasks

| When | Task |
|---|---|
| Daily | Check `/api/v1/health/ready` and the Monitoring tab for dead jobs and failed transactions |
| Weekly | Review the relayer's balance on any public network, and the audit log for `session.reuse_detected` |
| Monthly | Run a restore drill, review drift, apply dependency updates |
| When data changes | Retrain, review, and promote |

## Health and logs

- `/api/v1/health/live`: the process is up.
- `/api/v1/health/ready`: the database is reachable, with the model and chain status. Only the database affects readiness, because the app still serves its other features without a model or chain.
- Logs are JSON on stdout, one object per request, with a `request_id`. The same ID is in the `X-Request-ID` header, error responses and audit rows. Bodies, tokens and query strings are never logged.
- **Error monitoring:** unhandled exceptions are logged as `unhandled_exception` with a stack trace. Alert on that event and on 5xx responses in your log platform. No third-party error service is bundled.

## Backups

Dump to a file inside the container and copy that file. **Do not use `>` or pipe a dump through Windows PowerShell:** version 5.1 re-encodes text, which can corrupt non-English characters. A changed address would then fail its hash check permanently.

### Back up

```powershell
docker compose exec -T mysql sh -c 'mysqldump --single-transaction --no-tablespaces --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --result-file=/tmp/backup.sql "$MYSQL_DATABASE"'
docker compose cp mysql:/tmp/backup.sql backup.sql
```

Also back up these, which are not in the database:

- `storage/`: uploaded images and documents.
- `ml/artifacts/`: the model. The active model cannot be recreated byte for byte without its dataset.

Salts are in `blockchain_records`. **If they are lost, existing on-chain hashes can never be verified again,** so keep backups as carefully as the data they protect. Backups contain private data, so encrypt them.

### Restore

```powershell
docker compose cp backup.sql mysql:/tmp/restore.sql
docker compose exec -T mysql sh -c 'mysql --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" < /tmp/restore.sql'
cd backend
alembic -c alembic.ini upgrade head
```

Restore into an empty database. Then check integrity on a few registered properties: any difference from the chain is reported per field.

This method was tested by restoring into a separate database: a record containing non-English characters matched byte for byte, and row counts and the schema revision matched. Restoring **into a running application's own database** has not been rehearsed.

## Model management

### Scheduled retraining

Retraining only ever produces a candidate, so it is safe to schedule. An example with Windows Task Scheduler:

```powershell
$action = New-ScheduledTaskAction -Execute "$env:USERPROFILE\.venvs\proptwin\Scripts\python.exe" -Argument "ml\scripts\train.py --data ml\data\latest.csv --real" -WorkingDirectory "C:\path\to\proptwin-ai"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 3am
Register-ScheduledTask -TaskName "PropTwin retrain" -Action $action -Trigger $trigger
```

Providing fresh data is your responsibility. Retraining on unchanged data changes nothing.

### Promoting

On Administration, Models: review held-out metrics against the baselines and the interval's coverage, then approve and activate. A model that lost to its baseline cannot be approved.

### Rolling back

Retire the active model, approve the earlier retired version, then activate it. Past estimates stay linked to the model that made them.

### Monitoring quality

The Monitoring tab reports a population stability index on predicted values against the training prices, once 30 predictions exist.

| PSI | Read as |
|---|---|
| Under 0.1 | Stable |
| 0.1 to 0.25 | Watch |
| Over 0.25 | Large shift: investigate and retrain |

**This measures drift, not accuracy,** because the app does not collect actual sale outcomes. Real quality monitoring needs a feed of sale prices to compare against, which is a future improvement.

## Background jobs

Jobs retry with exponential backoff (15s, 30s, 60s, 120s), then become `dead` after 5 attempts. Dead jobs are kept and shown on the Monitoring tab. To retry one after fixing the cause:

```sql
UPDATE background_jobs SET status='queued', attempts=0, run_after=UTC_TIMESTAMP(6) WHERE id='<id>';
```

## Blockchain reconciliation

The worker checks open transactions on every pass, every 5 seconds by default, so no manual step is needed. If a node was down, transactions settle when it returns. Transactions the network has forgotten are marked `failed` after 30 minutes. The Transactions tab shows failures with reasons.

## Data retention

The worker purges daily:

| Data | Rule |
|---|---|
| Audit logs | Older than `AUDIT_RETENTION_DAYS` (default 730) |
| Refresh and account tokens | 30 days after expiry |
| Read notifications | After 1 year |
| Succeeded jobs | After 30 days |

Valuations, snapshots, simulations and chain records are never purged. Check these periods against the law where you operate.

## Dependency updates

Versions are pinned exactly in `backend/requirements.txt` and the lockfiles.

1. Update one group at a time: Python, frontend, or contract.
2. Run all the suites in [Testing](TESTING.md).
3. Retrain after upgrading PyTorch, scikit-learn or NumPy. The saved preprocessor may not load across versions, and the integrity check will not catch that kind of failure until you try.
4. Check `pip-audit` and `npm audit` monthly.

## Deployment rollback

1. Redeploy the previous image.
2. If it needs an older schema, roll back first: `alembic -c alembic.ini downgrade <revision>`. Downgrades drop columns, so back up first.
3. Check `/api/v1/health/ready`.

Migrations are tested in both directions on MySQL. MySQL cannot undo schema changes in a transaction, so a migration that fails halfway needs manual cleanup.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `model_unavailable` | No active model, or the artifact failed its integrity check | Activate a model. Check the artifact directory is mounted and unmodified |
| Signed out on every reload | Frontend and API are on different sites | See "same site" in [Deployment](DEPLOYMENT.md) |
| Signed out with `session.reuse_detected` in the audit log | A refresh token was replayed after the grace window, possibly stolen | Treat as a security event. The user signs in again |
| `Access denied` from MySQL on startup | `DATABASE_URL` points at another MySQL on port 3306 | Use port 3307, or fix the credentials |
| `missing_on_chain` | The local node restarted | Redeploy, and register again |
| Transaction `failed: unreachable` | Node down, or wrong `BLOCKCHAIN_RPC_URL` | Check `/api/v1/blockchain/network` |
| Transaction `failed: Rejected by the node` | The contract would revert, or the relayer is out of funds | Read the stored reason |
| A commit says `transaction_in_progress` | An earlier one is open, or a wallet call was never sent | Wait, or discard it on the Transfers page |
| Estimates warn that the market index is out of range | Time has passed since training | Retrain on newer data |
| `npm install` very slow | The project is in a synced folder such as OneDrive | Move it, or pause sync |
| Playwright says test files "are not regular files" | OneDrive turned them into cloud placeholders, which test runners skip without warning | Move the project out of OneDrive, or set the folder to "Always keep on this device" |
