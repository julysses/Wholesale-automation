# Evidence scan attestations — local signed observation ledger

Status: local migration and internal signing contract; not applied or activated. No signing key has been provisioned in production. No HTTP scan/persist workflow, safe preview, quarantine release or review approval binding is implemented by this increment.

## Inventory and mapping

Read-only inspection on October 29, 2026 confirmed production still has 95 migrations, latest `20261023221455`, no acquisition evidence registry, verification-key or verification-ledger tables, and zero Storage buckets. Existing pgcrypto is installed in `extensions`. The prior full schema inventory and local registry migrations remain the baseline. This increment inspects/reuses existing workspace memberships, profiles, sessions, ad campaigns, artifact/policy/revocation records and immutable audit machinery; it does not create another property, owner or campaign system.

| Logical record | Local table | Relationship and isolation |
| --- | --- | --- |
| Reviewed verification signer | `private.acquisition_evidence_verification_keys` | Workspace FK; empty deployment-controlled configuration; RLS, no application/service-role table grants. |
| Immutable scan observation | `public.acquisition_evidence_verifications` | Composite workspace/campaign/artifact and workspace/key FKs; RLS for current owners/admins and the recording operator; no application writes or mutation. |

Migration `20261029184129_acquisition_evidence_attestations.sql` creates these records, indexes and functions additively. It checks pgcrypto's existing namespace instead of silently moving an installed extension. The local fixture installs the extension when absent; no remote extension changes were made.

## Signing and database validation

`build_scan_attestation` accepts only strict internal scanner output plus trusted actor/session/request identity and a server-supplied `VerificationSigningKey`. It validates exact versions, scope, ordered timestamps, byte bounds, current retention, a maximum 24-hour key window and all non-approval flags. It emits deterministic compact JSON for twelve observation fields, never a secret. The key dataclass suppresses the secret in its representation. No environment key fallback or default key exists.

The HMAC-SHA256 message is the literal domain `acquisition-evidence-attestation-v1`, then newline-separated request, workspace, campaign, artifact, actor, session and key UUIDs, then the exact observation JSON text. Every identifier and payload byte is signed. Production provisioning must use an independently generated 32-byte key per environment/scope, reviewed scanner/signature version, approval reference and validity window. Never use the synthetic test key. Rotate to a new key identity; retain old rows for audit references and revoke obsolete keys. Key deployment, custody, rotation and incident procedures remain approval-sensitive deployment work.

The public invoker wrapper calls a private definer function with an empty search path. Actual authenticated role, MFA, current workspace membership, approved profile, matching live session and artifact access are required. The function locks the workspace, membership/profile/session, verification identity and artifact, then key and policy rows. Session deadlines are rechecked after waits. Operators can record only their own registered artifact; owners/admins can review within their workspace. Signature comparison examines all 32 bytes without an early mismatch exit; this is not a general database timing-side-channel certification.

The database rejects absent keys, forged signatures, unknown/duplicate JSON keys, coerced values, unsupported scan versions/statuses, altered metadata, revoked/expired keys, revoked artifacts, invalid retention policies, expired retention and observations older than 120 seconds. New observations are allowed while acquisition execution is paused so that security observations can be recorded; recording never enables execution.

## Recovery, history and limits

One request identity records one immutable observation and audit event. Simultaneous exact retries append once. Changed reuse conflicts. Preserve the entire signed request, including exact JSON text and original actor/session, after an uncertain write; do not rebuild it with new timestamps or another ID. The persistence transport and durable pending-request handling are still to be built. An exact historical retry can return its original receipt after signer/artifact revocation, but still requires the original current authorized session. Such a receipt is historical evidence of storage, not current clearance.

Both `no_detection` and `detected` can be recorded. The receipt says `observation_persisted=true`, while preview, content approval and execution remain false. Existing artifact state remains `pending_verification`; the ledger is not yet consumed by approval or preview. Durable quarantine state, protected review selection and locked approval binding must consume the ledger before any file is released. A later clean observation must not silently erase a detection.

The signed projection contains metadata, not file bytes, URLs, raw malware signatures or secret material. It is bounded to 4 KiB at the RPC boundary. Read visibility is current-role based; audit session IDs are retained without an auth.sessions FK so session removal does not destroy historical context.

## Validation and compensation

Disposable database tests exercise exact retries, changed signatures/context, strict metadata, detected history, key and artifact revocation, cross-workspace/role/MFA/session denial, operator visibility, raw-table/key privileges, immutable rows, simultaneous writers, session expiry while waiting, and populated-upgrade preservation. Python tests use real HMAC with synthetic keys and reject altered or approving scanner output. The application workflow connects a synthetic scanner through the real Python signer to the disposable SQL function. All 657 combined evidence/API tests passed in 21.15 seconds; all 43 application-to-PostgreSQL workflows passed in 351.835 seconds. All seven isolated migration tests passed in the final rerun in 55.771 seconds after the scanner-version constraint and duplicate-field test. These tests do not establish real PostgREST/JWT or live scanner acceptance.

All changes remain local until approved deployment. Leave the signing configuration empty and the internal path uncalled as the immediate hold. If a future deployment must be compensated, revoke signing keys and stop the signing worker, retain immutable observations/audit history, and use a reviewed forward-only migration to revoke function execution if needed. Do not drop history or disable RLS. A transaction failure during this migration rolls back its schema changes.

References: [Supabase database functions](https://supabase.com/docs/guides/database/functions), [PostgreSQL pgcrypto HMAC](https://www.postgresql.org/docs/current/pgcrypto.html#PGCRYPTO-HMAC), consulted October 29, 2026.
