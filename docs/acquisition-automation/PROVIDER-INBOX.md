# Acquisition provider inbox

Implementation: `20261026153314_acquisition_provider_inbox.sql`. This is an inert database foundation, not a live Facebook integration.

The existing `webhook_jobs` table is reused. Catalog inspection found its UUID primary key, JSONB payload, text status/source, attempts and timestamps, enabled RLS and no browser policies. Source migration 013 has the pending/created index. Existing Retell receipt and monitoring consumers remain separate. The isolated fixture recreates inspected columns/constraints, includes a legacy sentinel, and deliberately gives browser roles an overly permissive legacy policy to test the restrictive acquisition boundary.

## Routing and acceptance

A private integration maps a provider/account uniquely to a workspace. It defaults disabled; enabling requires an approval reference. Browser and service roles cannot edit configuration. Identity cannot be reassigned; disable rather than delete. Configuration changes append audit records. This is privileged release configuration pending its operator workflow, not a per-request caller-supplied workspace.

The service-only `accept_acquisition_event` RPC requires enabled global activation, enabled integration and active workspace, holding locks through commit. The caller must authenticate the provider over the raw request before calling it. This RPC does not verify signatures itself, and is not yet connected to an HTTP handler.

A receipt stores one canonical event payload, original raw request bytes, hashes, event type, external identity, integration/workspace and retention deadline. Raw input is bounded at 1 MiB. Use a minimal per-event payload for deduplication, excluding delivery-envelope timestamps that legitimately change on retries. The raw body retains the first accepted envelope. A retry with identical canonical payload returns the original receipt; conflicting payload for the same identity fails. The unique key and transaction advisory lock protect concurrent retries. No CRM lead or contact permission is inferred.

Acquisition records have source `acquisition_inbox` and status `acquisition_received`, never legacy `pending`. The existing generic drain therefore cannot claim them, even before worker code changes. A future dedicated lease/processor migration must preserve this boundary. These states intentionally do not claim processing or successful CRM ingestion.

## Access, retention and compensation

Raw receipts are server-only. Restrictive RLS excludes them from browser roles even if a permissive legacy policy exists. Application service-role raw writes cannot change/delete receipts, strip workspace scope or reset them into the legacy queue. Public RPC wrappers use invoker rights; privileged functions live in the private schema with explicit grants and empty search paths, following [Supabase function security guidance](https://supabase.com/docs/guides/database/functions).

Integration retention is configurable from 1–90 days, default 30; this engineering default requires review before activation. `purge_acquisition_payloads` performs a bounded, concurrent-safe batch after each stored deadline, removing raw bytes and JSON answers while retaining identity/hashes and an immutable purge audit. A purged receipt becomes `acquisition_expired`; it cannot be revived by a replay. No scheduler is installed. A monitored retention runner is required before accepting live payloads. Receipt metadata retention and legal holds remain policy work.

Compensation: disable the integration and its application receiver/worker. Keep schema/receipts for audit and run approved retention; never drop or replay historical migrations. Global acquisition activation also blocks new acceptance. Purging remains possible while activation is off. No production SQL is authorized by this implementation.

## Remaining delivery work

Dedicated lease/claim/completion and credential/error reconciliation; authenticated provider HTTP ingestion with persistence before acknowledgment; atomic batch handling; account/Page subscription verification; supported Meta fields/permissions/API review; token storage; controlled lead retrieval; canonical identity resolution; seller intake and attribution; monitoring and retention scheduling; full-schema upgrade and real PostgREST acceptance. Existing Facebook inline handler and legacy queue semantics are unchanged. No production release gate is met by the isolated inbox tests alone.

## Recoverable claims and deferral

Migration `20261026153939_acquisition_inbox_leases.sql` adds private processing state keyed by the existing immutable receipt. It initializes state transactionally when a receipt is inserted and covers preexisting acquisition receipts. Legacy receipts receive no processing row. No application role can read or mutate the private table directly.

`claim_acquisition_events` is service-only and takes an exact configured integration, a bounded batch of 1–20, and a 30–300 second lease. It rechecks global activation, enabled integration and active workspace, locks eligible receipts/processing rows with `SKIP LOCKED`, and returns canonical event data plus a new random lease token. It omits the full raw envelope. Concurrent workers cannot claim the same active lease. A lost claim response or worker crash is recoverable after expiry; recovery replaces the token so the former worker cannot settle the event.

`defer_acquisition_event` accepts only allowlisted retry/review outcomes. Timeouts, rate limits, provider unavailability and persistence failures receive exponential server-side backoff. Invalid credentials, permission denial, invalid data, identity conflicts and unsupported events are parked for review. Freeform exception text is rejected to avoid persisting secrets. Five attempts is the current hard limit; both failed fifth attempts and abandoned fifth leases park with `RETRY_EXHAUSTED`. Expired/purged payloads park with `PAYLOAD_EXPIRED` without being returned to a worker. Same-token identical deferral retries return the saved outcome without another audit; changed outcomes or stale/expired tokens fail.

Claiming stops on suspension or disabled activation/integration. Deferral remains available after these switches so in-flight work can record a safe hold. No generic success RPC exists: completion must be an atomic provider-specific transaction that writes canonical intake and verifies the current lease. This prevents a queue marker from being mistaken for successful CRM ingestion. Claims and deferrals append scoped audit records without exposing lease tokens.

Remaining: atomic successful intake completion, explicit reviewed recovery from held jobs, actionable credential alerts/operator queue, actual provider worker wiring, polling schedule and monitored retention. No worker runs merely by applying this migration. Compensation is to disable the integration/worker; leases expire and evidence remains. Do not reset private processing rows manually as an application recovery procedure.
