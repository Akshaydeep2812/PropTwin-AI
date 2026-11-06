# Security

This documents what has been built and tested. It has not had an independent penetration test or contract audit.

## Controls

| Risk | Control | Tested |
|---|---|---|
| Stolen password database | Argon2id hashes. Login timing is equalized for unknown accounts | Yes |
| Privilege escalation | Registration accepts only `owner` or `investor`, and unknown fields are refused. Admins cannot change their own account | Yes |
| Broken access control | Role checks and per-object checks, both on the server | Yes |
| IDOR | Records a caller may not see return 404, so IDs cannot be probed | Yes |
| SQL injection | Bound parameters throughout. Sort fields come from a fixed list | Yes |
| XSS | React escapes output. The access token lives in memory, and the refresh token is `HttpOnly` | Partly: no dedicated scan |
| CSRF | The cookie is `SameSite=Strict`, limited to the auth routes, which also need a custom header | Yes |
| Stolen refresh token | Single use, stored only as a hash. Replay after the grace window revokes the whole session family | Yes |
| Session after logout | Access tokens are checked against the session, so logout takes effect immediately | Yes |
| Brute force | Rate limits on login, registration and password reset | Yes |
| Malicious uploads | Type decided from file bytes. Server-generated storage names. Documents download as attachments | Yes |
| Tampered model | SHA-256 digests are checked before the pickle is loaded, and the manifest digest is pinned in the database | Yes |
| Secrets in code | All from the environment. Production refuses placeholders and public Hardhat keys | Yes |
| Forged transaction hashes | Sender, contract and call data are checked on-chain | Yes |
| Dictionary attacks on hashes | A per-record 32-byte salt, kept off-chain | Yes |
| Personal data on-chain | Only hashes and addresses. Real transaction data is inspected in a test | Yes |
| Missing audit trail | Sensitive actions write audit rows in the same transaction | Yes |

## Roles

| Capability | Guest | Owner | Investor | Verifier | Admin |
|---|---|---|---|---|---|
| Browse public listings | Yes | Yes | Yes | Yes | Yes |
| See street address and sale history | | Own | | Under review | All |
| Create and manage properties | | Own | | | All |
| Request valuations | | Yes | Yes | Yes | Yes |
| Create a twin | | Own | | | All |
| Run scenarios | | Own | Listed | | All |
| Commit records on-chain | | Own | | | All |
| View private documents | | Own | | Under review | All |
| Decide verification | | | | Not their own | Not their own |
| Manage users, models and audit logs | | | | | Yes |

## Known trade-offs and gaps

- **Refresh grace window:** a rotated token stays usable for 10 seconds, so that two tabs refreshing together do not end the session. A token stolen and used inside that window is not detected.
- **Custodial relayer:** a record registered without a linked wallet is controlled by the server's key until handed over. Compromise of that key affects all such records, so keep it in a secret manager, and fund it minimally.
- **Model files use pickle:** this is safe only because digests are checked first. Anyone able to change both the artifact and the database could still run code.
- **Rate limits are per process and per IP.** Users behind one shared address share a limit, and several API processes each count separately.
- **Documents are not encrypted at rest** by the application. Use an encrypted disk.
- **No multi-factor authentication.** Add it before giving real administrators access.
- **Email verification is not enforced.** Accounts work before it is completed.
- **Verifiers can read any property with a request on it,** not only those assigned to them.
- **Malware is not scanned for** in uploads, beyond the type check.
- **Audit rows can be changed** by anyone with direct database access. Ship logs elsewhere if you need stronger guarantees.

## Reporting and rotation

- **Signing secret:** changing `SECRET_KEY` signs everyone out, which is safe to do at any time.
- **Relayer key:** deploy a new key, grant it `REGISTRAR_ROLE` from the admin key, then revoke the old one.
- **Suspected leak of `.env`:** rotate all of the above and the database password, and review the audit log.
