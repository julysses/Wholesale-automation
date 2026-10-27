# Inbound seller intake — implementation and release gates

Status: local lifecycle ledger and disabled signed receiver implemented; live acceptance pending. Phase 2 is not activated. Facebook and shared-foundation gates remain prerequisites for activation.

## Existing application boundary

`tools/retell_adapter.py` is an outbound Retell/Air calling adapter. `web/api/webhooks.py` also handles legacy voice and paused chat/SMS receipts, including transcript processing and downstream actions. Do not repurpose those paths for acquisition inbound traffic without an explicit compatibility and tenancy review. No changes to those paths were made in this increment.

## Verified provider contract

Official documentation reviewed October 26, 2026:

- [Retell webhook overview](https://docs.retellai.com/features/webhook-overview): lifecycle retries are deduplicated by event plus call ID. Transfer attempts need additional identity. Started events can be absent for unconnected calls. Authentication must verify the raw request body with the provider's supported signature verifier.
- The same documentation states webhooks carry full call data regardless of storage setting; basic-attributes storage does not suppress webhook recordings/transcripts. Therefore storage opt-out is not evidence that recording or transcription is disabled. The PRD's legal and technical recording/transcription gate remains unresolved.
- [Voice agent configuration](https://docs.retellai.com/api-references/update-agent) supplies agent configuration/version context. No agent, phone number, routing, credentials or settings were created or changed here.

## Implemented offline parser

`tools/acquisition_inbound_events.py` accepts a decoded lifecycle event plus independently resolved workspace/integration, exact agent ID/version and acquisition number. The dedicated receiver supplies these arguments from trusted server configuration; webhook metadata cannot establish them. It accepts only phone calls explicitly marked inbound and matching the configured destination and agent version. Invalid types, interval conflicts and mismatched routes reject with fixed codes.

The output is an explicit metadata allowlist: scoped call/event identity, configured agent/version, provider status, timestamps and a boolean noting known sensitive-content fields. It never copies caller number, destination number, metadata, dynamic variables, transcript, recording links, analysis or seller answers. Unknown fields are discarded. The presence boolean is diagnostic, not proof that all sensitive content was detected or recording was disabled. Its hash is an integrity checksum, not authentication.

Scoped event keys distinguish started, ended and analyzed events for one call. Reconciliation checks every projected row, accepts identical retries, handles event order independently and accepts terminal events without a started event. Conflicting same-event retries, terminal statuses or timestamps require review. Analysis receipt is not qualification. Every result has no permitted actions and no execution authority.

Transcript/chat/transfer events and legacy aliases are deliberately unsupported by this initial parser. Transfer support must preserve repeated attempt identities; do not deduplicate them by call ID alone. The parser does not verify signatures, persist receipts, create leads, route calls, request callbacks, transfer a caller, or authorize recording.

## Next implementation and acceptance

1. Completed locally: read-only catalog inspection, scoped call_events ledger, immutable audit, concurrent replay tests and populated legacy fixture preservation. Full production upgrade remains outstanding.
2. Completed locally: dedicated default-disabled receiver, bounded raw-byte verification, fixed server routing and metadata-only durable acknowledgment. No raw archive is implemented or authorized.
3. Completed locally: changed-retry rejection and unknown-commit HTTP-to-SQL handoff test. Actual PostgREST/JWT and approved provider delivery acceptance remain outstanding.
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


## Signed receiver (local implementation, default disabled)

`POST /webhooks/retell/acquisition` is registered separately from the legacy `/webhooks/retell` and `/webhooks/retell/call` handlers. It does not use their transports, settings fallbacks, transcript storage or downstream processing. Both `ACQUISITION_ENABLED` and `ACQUISITION_INBOUND_WEBHOOK_ENABLED` must be exactly true (case-insensitive); absence disables receipt handling. Database activation, integration, route and approval-reference checks remain independently enforced on every acceptance.

Required server configuration:

| Variable | Purpose |
| --- | --- |
| `ACQUISITION_INBOUND_SECRET` | Retell API key with webhook badge, supplied through approved secret management |
| `ACQUISITION_INBOUND_SERVICE_KEY` | Dedicated configured server ingestion credential; no generic-key fallback |
| `SUPABASE_URL` | Fixed HTTPS database origin without credentials/path/query/fragment |
| `ACQUISITION_INBOUND_WORKSPACE_ID` | Canonical workspace UUID |
| `ACQUISITION_INBOUND_INTEGRATION_ID` | Canonical reviewed Retell integration UUID |
| `ACQUISITION_INBOUND_AGENT_ID` | Exact configured agent |
| `ACQUISITION_INBOUND_AGENT_VERSION` | Nonnegative PostgreSQL integer version |
| `ACQUISITION_INBOUND_ACQUISITION_NUMBER` | Exact E.164 receiving number |

This first endpoint supports one configured route per deployment. It does not accept tenant IDs or route overrides from metadata, query parameters or caller input. The dedicated environment name does not itself narrow Supabase service-role privileges; use server-only secret controls, and do not expose the credential to browsers.

The [current Retell signature contract](https://docs.retellai.com/features/secure-webhook) uses `X-Retell-Signature: v={milliseconds},d={hex}` with HMAC-SHA256 of original body bytes followed by the decimal timestamp. The receiver uses constant-time digest comparison and a five-minute past/future window, rejects duplicate signature headers, caps streamed bodies at 1 MiB and rejects duplicate JSON keys, non-finite constants, invalid UTF-8 and invalid lifecycle/routing shapes. No raw request body, transcript or caller number is written or logged by this adapter. Infrastructure request-body logging must also remain disabled before live use.

Only the allowlisted projection and configured integration/receiving number reach the service RPC. HTTP 204 is returned only after a strict receipt response proves a canonical record ID, matching workspace, boolean replay status and no execution authority. Persistence errors, timeouts, wrong-scope or malformed success responses yield sanitized retryable 503; the adapter performs no internal retry. Provider redelivery reconciles the original transaction through ledger identity. Changed retry or route revocation remains unacknowledged and requires operational review. Oversize events return 413; unsupported or malformed events return 400; invalid signatures return 403.

Validation covers the actual application registration/middleware with simulated database responses, plus a disposable real-SQL workflow with commit-before-response loss, exact replay, changed retry and route revocation. This is not live provider acceptance or real PostgREST verification. Lifecycle receipt alone creates no seller intake or callback and cannot satisfy the Phase 2 gate. Sensitive-content detection is diagnostic only; approved provider recording/transcription controls, disclosure behavior and structured authenticated tools remain required.

## Structured tool preparation contract (offline only)

The [Retell custom-function contract](https://docs.retellai.com/build/single-multi-prompt/custom-function), reviewed October 26, sends a wrapped `name`, `call`, `args` payload unless args-only mode is enabled. Call context can contain transcripts. Retries repeat requests, and a caller interruption does not cancel an executing request. Our acquisition configuration must use the wrapper and verify its original signed bytes before processing; tool responses must never reveal private owner data or internal underwriting.

`tools/acquisition_inbound_tools.py` now prepares three strict tool intents: `submit_seller_intake`, `request_callback`, `request_human`. This pure module is not exposed as an HTTP endpoint and does not authenticate or persist anything. It requires exact configured inbound agent/version/number and ongoing call status. Unknown top-level/tool argument fields reject, including model-supplied tenant/lead/approval fields. Provider metadata and transcripts are discarded.

Every intent requires a canonical `request_id` and nonnegative `expected_revision`. These are retry/concurrency inputs, never credentials. The deterministic request hash includes trusted scope/call/agent, tool name, request identity, expected revision and bounded structured evidence; it excludes changing transcripts and metadata. Future persistence must serialize by call plus tool/request identity, reject changed retries, compare revisions and recheck nonterminal call state and route approval atomically. A matching signed call object alone is insufficient authority after a terminal ledger event or revoked route. Do not acknowledge preparation as saved data.

- Intake uses an `answers` object of canonical seller fields, string values up to 2,000 characters. Shared `normalize_seller_fields` now serves Facebook and inbound preparation without inventing Facebook identifiers or form consent. Missing/ambiguous price stays unknown; assertions never verify ownership/property or qualify a canonical territory. Initial intake updates are complete submitted snapshots; persistence must retain prior versions and not silently patch or merge properties.
- Callback requires explicit caller-request assertion, supplied phone, preferred-time text and purpose. It never falls back to caller ID. Existing US phone normalization produces an unverified candidate or an explicit review gap. No parsed appointment, channel consent, scheduled call or execution permission is created. Live execution still requires fresh eligibility under the approved policy.
- Human escalation records a bounded reason/details and distinguishes caller-requested help from agent-detected unsupported language, failed transfer, sensitive situation or inability to finish. It does not claim a completed transfer or authorize one.

Existing seller_intakes requires a Facebook receipt and source type; it cannot accept these intents without a reviewed additive extension. Next work must map call-scoped revisions into the existing intake/task entities, add immutable evidence and atomic audit, authorize server-only writes against current call state, and implement minimal safe tool responses. No parallel CRM, live tool registration, database changes or follow-up action was added by this parser increment.

## Task dependency acceptance checkpoint

The inspected existing `tasks` relation is now restored in the disposable database before acquisition boundary migrations. Focused tests cover mandatory title, genuine defaults, outgoing parent FKs, legacy edit/read compatibility, workspace-bound read/write restrictions and the remaining call-only/TRUNCATE/TRIGGER gaps. The catalog also identifies seven county-ingestion FK dependents that must be preserved in full production upgrade testing. See SCHEMA-MAPPING.md for mapping and fixture limits. No production DDL or task records were changed.

## Persisted callback and escalation review requests (local migration)

`20261027013724_acquisition_inbound_review_tasks.sql` extends existing tasks with workspace/integration/call identity, immutable request UUID, per-call/per-kind revision, bounded evidence, database-computed request hash and optional normalized callback phone. Existing rows retain null acquisition columns, IDs, defaults and behavior. Scoped records deliberately have no CRM parent, assignee, due date, completion time, priority or legacy description. Their fixed `acquisition_review_required` status and `acquisition_inbound_review` type do not authorize dialing, transfers or scheduling.

The service-only `record_acquisition_inbound_request` RPC accepts configured integration/number/agent/version, call ID, request UUID, expected revision, request kind and strict evidence. It accepts only request_callback and request_human; submit_seller_intake persistence remains separate pending work. Route configuration, activation, enabled Retell integration and active workspace are locked and checked. Evidence fields are allowlisted and bounded; callback requires an affirmative request assertion, while escalation allows documented agent-detected reasons. Database contact normalization produces a candidate or null; it never verifies the phone or creates permission. The database normalization supports explicit international country codes, while the current pure tool preview only normalizes US numbers; persistence is authoritative and this discrepancy must not become permission or identity proof.

A request-identity lock prevents reuse across calls/kinds. A second lock is identical to lifecycle ingestion's call lock. A new write requires an ongoing started ledger event, no ended/analyzed event, and matching latest revision for that call/kind. Exact retries return the original task, including after a later terminal event; changed retries conflict and cannot overwrite. Disabled routes/integrations deny even retry confirmation. New task plus minimal audit are one transaction. Audit holds identifiers/hash, not callback details or private contact text.

Direct browser queries exclude all scoped tasks. The bounded `acquisition_inbound_requests(workspace,integration,call,after,limit)` RPC requires current owner/admin/operator membership; caller/unrelated/revoked members cannot read evidence. It returns at most 50 immutable historical requests and no execution authority. These rows are review evidence, not an already reconciled latest-only operator queue. The later queue must distinguish superseded revisions and add explicit reviewed completion through separate audited records, not mutate original evidence.

Scoped task updates/deletes and direct service inserts are blocked; application/service TRUNCATE/TRIGGER grants are removed. Existing task references from county ingestion are preserved. The migration uses private DEFINER implementations with empty search paths and public INVOKER wrappers and explicit grants, consistent with [Supabase function security guidance](https://supabase.com/docs/guides/database/functions#security-definer-vs-invoker). The privileged database owner remains trusted; these controls are not protection against a superuser changing DDL.

Compensation: disable the inbound tool receiver (not yet implemented) and route; preserve tasks and audit. If an emergency database stop is needed, an authorized operator can revoke execution on both record RPC wrappers. Do not drop columns, delete request history or restore truncate/trigger privileges. No production migration or live tool is enabled. Actual signed-tool HTTP, seller-intake persistence, operator review UI, callback eligibility/execution and full county-dependent upgrade acceptance remain outstanding.

## Signed callback/escalation tool endpoint (local, default disabled)

`POST /webhooks/retell/acquisition/tools` now shares the lifecycle receiver's raw-byte signature verification, five-minute timestamp window, one-signature requirement, 1 MiB stream cap and strict JSON parser. It additionally requires `ACQUISITION_INBOUND_TOOLS_ENABLED=true`; acquisition and inbound-webhook flags and dedicated route/secret configuration must also be enabled. This is code availability, not permission to enable provider tools.

Only wrapped request_callback and request_human intents are accepted. submit_seller_intake remains rejected until its persistence transaction exists. Args-only mode, unrecognized fields, caller-supplied scope, wrong agent/version/number, unsupported tools and non-ongoing request call objects cannot reach persistence. The raw signature covers provider call context, but metadata/transcripts/recordings are not forwarded to the database.

The client maps only configured routing and explicit validated call/request/revision/kind/evidence into record_acquisition_inbound_request. It makes one database attempt with the dedicated server key, bounded timeout and redirects disabled. A success response must have exactly the expected receipt fields, canonical task ID, matching workspace, expected next integer revision, boolean duplicate status and execution_authorized=false. Timeout, conflict, disablement, database error or malformed/wrong-scope response returns a fixed 503; no private upstream errors or invented successful save. Retry must preserve the original request UUID/revision/evidence. A new UUID is not recovery for an uncertain commit.

The 200 response exposes only review status, the submitted request UUID, confirmed revision, replay flag and explicit no-execution authority, plus neutral wording that saving the request does not schedule a callback or initiate a transfer. It contains no internal task/workspace ID, phone, seller evidence or underwriting. Provider responses are conversational content; an agent must not promise a callback time, approved offer or successful transfer based on this response.

HTTP tests use the actual application and simulated PostgREST. A real-SQL workflow additionally proves missing call-ledger denial, lost response after committed task, duplicate recovery, changed retry conflict, human-review persistence, terminal-call denial of new requests and revoked-route denial. Production migrations, actual provider registration/privacy review, real PostgREST/JWT acceptance, operator task review and seller-intake persistence remain pending.

## Inbound seller-intake persistence (local migration)

`20261027015624_acquisition_inbound_intakes.sql` extends seller_intakes with reviewed integration/call/started-event origin, request UUID and revision. Existing Facebook rows still require their original webhook receipt and retain their data. Inbound rows instead require the composite scoped route and call-event references; they never fabricate a Facebook receipt. The service-only record_acquisition_inbound_intake RPC checks activation, route/agent/version/number, active workspace, bounded prepared answer schema and false verification/permission/execution flags. It accepts only incomplete, unqualified or requires_human_review as initial classifications.

The RPC shares the lifecycle call lock, requires a durable ongoing started event and no terminal event for a new revision, and compares expected revision. Same request UUID/call/revision/evidence confirms an existing commit (including after call completion); changed retries conflict. Route disablement denies all writes/confirmation. A first intake creates one existing CRM lead and workspace binding with SMS/email sequences disabled, AI calling paused and acquisition retention protection. Telephone/address matching does not merge it into another lead or assert a canonical property. Later revisions append immutable seller-intake rows on that same lead, preserving initial CRM assertions and prior records rather than rewriting a reviewed identity.

Attribution uses the existing acquisition_lead_sources relation with source_type=retell_inbound, provider call identity in external_lead_id, started-event reference and explicit inbound_revision. Facebook ad/form/campaign fields remain null. Each row describes an intake evidence revision; multiple revisions of one integration/call are not multiple acquired leads or independent marketing touches. Source-aware UI/reporting must group by provider identity for funnel metrics and distinguish revisions before live use; current legacy Facebook source cards are not inbound acceptance evidence. No conversion or cost aggregate is added here.

The qualification evaluator marks an older inbound revision SUPERSEDED_INBOUND_INTAKE when a newer row exists. This changes its assessment evidence and prevents it from remaining qualified/current for downstream analysis/offer review. New revisions need fresh identity and qualification review. Existing amount approval is still distinct from binding transmission; concurrent final transmission controls remain outside this migration.

Prepared answers are server-generated output of the shared normalizer, not caller-supplied permission. The service credential remains trusted and must only be used after signed-tool validation. This RPC does not accept a caller-supplied canonical lead/property, write contacts as verified, trigger underwriting or send an offer. The signed submit_seller_intake HTTP path remains disabled/rejected until client wiring, revision-aware read/UI handling and integrated acceptance are complete.

Compensation: keep inbound tools/routes disabled and revoke record-intake RPC execution through an authorized operator if needed. Preserve appended intake/source/audit history and CRM links; do not delete revisions, remove origin columns or rerun old migrations. Full production-schema/county-dependent upgrade and live provider/privacy approvals remain required. No production migration was applied.

## Channel-aware read and review surfaces

Intake list/detail APIs now include source_type, inbound integration/call identity and revision. Lead-source reads include inbound event/revision metadata. Local migration `20261027020314_acquisition_inbound_read_metadata.sql` adds inbound event/revision fields to the existing bounded property-source RPC without changing its membership checks, paging, association evaluation, writes or grants.

Intake review validates source-specific metadata, labels Facebook inquiries versus inbound call revisions and shows stable call/integration identity. It does not claim that a displayed snapshot is the latest; qualification must be refreshed before action. Inbound records do not load Facebook campaign review controls. Property sources label inbound evidence revisions and call identity, reject mixed or malformed origin/campaign claims, and explicitly distinguish evidence rows from unique lead/conversion totals. Historical revisions remain available; this is not a latest-only grouped operator queue or a funnel aggregate.

The existing source fixtures and component tests now exercise these channel boundaries. Browser visual QA for the new labels remains pending; component assertions, build and lint do not substitute for live provider acceptance. These read changes require the accompanying local migrations before enabling acquisition UI in a deployed environment. No production schema or feature flag was changed.

## Signed seller-intake submission (local implementation, default disabled)

The signed `/webhooks/retell/acquisition/tools` endpoint now supports submit_seller_intake in addition to review-only callback/escalation. Intake additionally requires `ACQUISITION_INBOUND_INTAKE_ENABLED=true`; absence disables only intake submission while leaving the separately gated review tools unchanged. No flags were enabled and no tools were registered with Retell.

The server prepares the complete submitted snapshot through the shared seller normalizer, adds seller-intake-v1 and forwards that prepared evidence to record_acquisition_inbound_intake. It never forwards transcript/recording metadata, caller ID, model-supplied tenant/property IDs or fabricated form consent. Each intentional new snapshot needs a fresh UUID and the prior confirmed intake revision. Exact uncertain retries retain UUID/revision/answers. Callback and human-review revisions remain separate counters; they cannot supply an intake revision.

A database response must have the exact intake receipt fields, matching workspace, canonical intake/lead IDs, expected next integer revision, boolean duplicate and false execution authority. The client does not expose internal lead/intake IDs or answer values to the provider agent. Its success message confirms property information was saved for review and does not claim an approved offer. Errors and malformed/uncertain replies stay sanitized 503 with no internal retry. Incomplete seller information remains incomplete; missing or ambiguous price is never zero-filled.

The HTTP-to-real-SQL journey now covers lost response after first commit, one lead across exact retry and new revision, no merge with an existing same-phone lead, immutable source revision reads, and invalidation of a saved qualified assessment after changed answers. A later terminal call permits confirmation of an existing commit but rejects new snapshots. CRM sequences stay disabled and no callback task, offer or provider operation is created by intake submission.

This completes local signed intake persistence wiring, not RET-003 or Phase 2 live acceptance. Property lookup with privacy-safe results, operator review queue, interruption/human-transfer behavior, provider configuration, approved recording/transcription controls, bilingual QA, real PostgREST/JWT and sequential Phase 1 acceptance remain outstanding. Earlier sections describing rejected/unwired intake refer to their implementation checkpoints; this section describes the current local code.

## Local browser QA checkpoint (October 26, 2026)

The actual intake and source components can be exercised without provider/database access using `frontend/tests/browser/inbound-review.vite.config.ts` and `/tests/browser/inbound-review.html` on localhost:5180. Run Vite from frontend. The adapter rejects all writes and offers a simulated read-access revocation checkbox.

Verified call revision labels, shared original lead across source revisions, hidden Facebook controls, operator restrictions, responsive wrapping and read-error clearing. Refresh intakes now also refreshes the selected intake evidence/qualification/access queries while retaining exact pending identity requests. Desktop/mobile screenshots are in the evidence directory. This is synthetic UI validation, not a live authentication/provider or Phase 2 acceptance result.
