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
