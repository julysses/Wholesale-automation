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
