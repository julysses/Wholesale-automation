# Inbound seller intake — implementation and release gates

Status: offline lifecycle foundation only. Phase 2 is not activated. Facebook and shared-foundation gates remain prerequisites for activation.

## Existing application boundary

`tools/retell_adapter.py` is an outbound Retell/Air calling adapter. `web/api/webhooks.py` also handles legacy voice and paused chat/SMS receipts, including transcript processing and downstream actions. Do not repurpose those paths for acquisition inbound traffic without an explicit compatibility and tenancy review. No changes to those paths were made in this increment.

## Verified provider contract

Official documentation reviewed October 26, 2026:

- [Retell webhook overview](https://docs.retellai.com/features/webhook-overview): lifecycle retries are deduplicated by event plus call ID. Transfer attempts need additional identity. Started events can be absent for unconnected calls. Authentication must verify the raw request body with the provider's supported signature verifier.
- The same documentation states webhooks carry full call data regardless of storage setting; basic-attributes storage does not suppress webhook recordings/transcripts. Therefore storage opt-out is not evidence that recording or transcription is disabled. The PRD's legal and technical recording/transcription gate remains unresolved.
- [Voice agent configuration](https://docs.retellai.com/api-references/update-agent) supplies agent configuration/version context. No agent, phone number, routing, credentials or settings were created or changed here.

## Implemented offline parser

`tools/acquisition_inbound_events.py` accepts a decoded lifecycle event plus independently resolved workspace/integration, exact agent ID/version and acquisition number. Those arguments must eventually come from trusted server configuration; webhook metadata cannot establish them. It accepts only phone calls explicitly marked inbound and matching the configured destination and agent version. Invalid types, interval conflicts and mismatched routes reject with fixed codes.

The output is an explicit metadata allowlist: scoped call/event identity, configured agent/version, provider status, timestamps and a boolean noting known sensitive-content fields. It never copies caller number, destination number, metadata, dynamic variables, transcript, recording links, analysis or seller answers. Unknown fields are discarded. The presence boolean is diagnostic, not proof that all sensitive content was detected or recording was disabled. Its hash is an integrity checksum, not authentication.

Scoped event keys distinguish started, ended and analyzed events for one call. Reconciliation checks every projected row, accepts identical retries, handles event order independently and accepts terminal events without a started event. Conflicting same-event retries, terminal statuses or timestamps require review. Analysis receipt is not qualification. Every result has no permitted actions and no execution authority.

Transcript/chat/transfer events and legacy aliases are deliberately unsupported by this initial parser. Transfer support must preserve repeated attempt identities; do not deduplicate them by call ID alone. The parser does not verify signatures, persist receipts, create leads, route calls, request callbacks, transfer a caller, or authorize recording.

## Next implementation and acceptance

1. Inspect live metadata and fixture coverage for existing `ai_call_records`, `call_events`, `call_transcripts`, `webhook_jobs`, intake and integration tables before additive SQL. Reuse equivalents and enforce actual workspace membership and composite tenant references.
2. Add a dedicated default-disabled inbound route with bounded raw-body verification and trusted integration/agent/number routing. Decide privacy-safe durable receipt storage and retention before accepting payloads; never log or store raw content through the ordinary metadata ledger.
3. Persist receipt/event identities transactionally, compare changed retries, and reconcile through the tested parser. Acknowledge only durable acceptance. Add concurrent and unknown-commit acceptance tests.
4. Implement authenticated property lookup, structured intake updates, callback request and human escalation tools. Caller ID alone must not establish ownership or merge properties. Callback requests still require fresh channel eligibility before execution.
5. Verify provider/Twilio controls for recording/transcription before live routing, approved Hilltop AI disclosure, no binding-offer/contract tools, interruption/silence/human-request/failed-transfer handling and bilingual QA before Spanish support.
6. Preserve sequential activation and require separate approved inbound acceptance. This document and offline parser do not satisfy the Phase 2 release gate.

## Persistence mapping checkpoint

Fresh read-only catalog inspection found existing call_events suitable for the lifecycle ledger extension: lead and phone are nullable, so no fabricated owner/contact is needed for a metadata-only event. Its required disposition needs a distinct lifecycle category and exclusion from legacy seller-outcome reporting. ai_call_records requires phone and has global call identity plus transcript/qualification dependencies; it is not the initial receipt target. Existing webhook_jobs remains the receipt equivalent. See SCHEMA-MAPPING.md and the saved catalog for exact constraints and access gaps.

Before any inbound ledger SQL, the isolated harness now includes actual call_events columns, constraints, indexes, policies and grants. Approved legacy users can still read unbound events and possess broad truncate/trigger privileges. The new scoped extension must explicitly close those paths for acquisition evidence while retaining legacy behavior where required. No inbound SQL or production schema change has been made at this checkpoint.

## Additive metadata ledger (local migration only)

`20261027010558_acquisition_inbound_event_ledger.sql` extends call_events with workspace, integration, call/event identity and the validated metadata projection. It creates no new call-summary or transcript table. Scoped rows use explicit `acquisition_retell_inbound` / `provider_lifecycle` categories; lead, phone, recording, notes and other legacy qualification fields stay null, with empty legacy raw_payload. Existing rows retain null acquisition fields and original behavior. General direct authenticated queries exclude the acquisition namespace; scoped reads use the controlled RPC.

`private.acquisition_inbound_routes` is privileged configuration tied to the existing Retell integration by composite workspace FK. It defaults disabled and requires privacy/disclosure/Phase 1 acceptance references before enabling. Those references document approval; they do not themselves verify provider controls. Route identity is immutable and audited. Initial support is one exact agent/version/number per integration; a reviewed route/version rotation workflow remains future work. There is no application role grant to configure or enable it.

The service-only `accept_acquisition_inbound_event(integration, number, projection)` RPC requires acquisition activation, enabled Retell integration, enabled route and active workspace under locks. It validates exactly 15 allowed projection fields, configured scope/agent/version/number, lifecycle/timestamps, stable event identity and Python-compatible canonical projection hash. This is a trusted ingestion boundary: a future HTTP adapter must still verify the raw signature and resolve routing independently before calling it. No browser or caller role may invoke ingestion.

Call-wide advisory locking plus the unique integration/call/event index makes concurrent exact retries return one record and one immutable audit. Changed retries reject with conflict rather than overwrite evidence. Disablement denies further receipts, including replay confirmation. A later operational recovery path must handle this without enabling routes or discarding uncertain records automatically.

A trigger forbids update/delete of scoped events and direct service-role insertion; application roles lose truncate/trigger grants. Private DEFINER functions have empty search paths and public wrappers are INVOKER. A scoped read RPC `acquisition_inbound_events(workspace, integration, call, after, limit)` permits actual owner/admin/operator membership, limits pages to 50 and returns no execution authority. Exact integration filtering avoids merging same-named calls across accounts. This follows the distinction between [RLS and grants](https://supabase.com/docs/guides/database/postgres/row-level-security); RLS alone does not remove broad table privileges.

This ledger is durable minimal receipt evidence, not a raw webhook archive. It intentionally does not use the existing inbox raw-body requirement until an approved inbound storage/retention policy is designed. No HTTP listener, provider registration, call routing, CRM intake or callbacks are enabled by this migration.

Compensation: keep inbound routes and integration disabled and stop the future ingestion adapter; preserve event/audit history. Revoke service execute on the public/private accept functions if an emergency write stop is required through the authorized database operator. Do not drop columns, replay earlier migrations, delete ledger rows or regrant truncate/trigger as rollback. Existing legacy event reads/writes remain compatible. No production migration has run; full populated production-schema and actual PostgREST/JWT acceptance remain required.
