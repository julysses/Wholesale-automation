# Acquisition automation — current implementation and release handoff

Updated October 31, 2026 (America/Chicago). The original PRD and IMPLEMENTATION-PLAN.md remain controlling. This page is current scope/status; chronological results and commands are in PROGRESS.md. Nothing here certifies production or provider acceptance.

## Publication and active process

- Published candidate: `ecca0f47b1df00f5215ab2062051307f37c52c6f` on `codex/acquisition-foundation`. Normal push confirmed `173684f` → `ecca0f4`; checkout was clean. Exact successor CI `41252309134` has four successful jobs, one backend failure, and the PostgreSQL contention job still running: https://github.com/julysses/Wholesale-automation/actions/runs/41252309134. Require all six terminal successes before another feature push. Predecessor 173684f / CI 41250516262 attempt 2 completed all six successfully after one runtime-install timeout. No live job was restarted.
- Predecessor `5ca649c` / CI `41246949570` completed successfully with all six jobs. Prior fixture repair `2f2dbe7` / CI `41245920319` also passed all six. No jobs cancelled or restarted.
- Contract draft schema/API/rules and seller choices are published in Git, not deployed. The fifth guided draft step is published in Git; synthetic desktop/mobile browser QA passed. Shared evidence regression rehearsal 80922 exited 0: 57 migrations, 26 access probes, 88 workflows, 54 gateway checks. No local test or preview process is active.
- Branch automatic deployment is disabled. No production migration, provider setting, spend, outreach, fulfillment or binding transaction was performed. Preserve paused SMS and existing county/CRM behavior.

## CI timing repair and local document interface

The backend failure in run 41252309134 is `test_rejects_unverified_wrong_context_or_stale_challenge[patch7]`: its future timestamp was computed during collection, then became past during the 73-second suite. The repair replaces collection-time timestamps with a fixed verification clock and six expiry/skew boundary cases. No production validation was loosened. Focused suite: 46 passed. CI-equivalent full local backend suite: 3,242 passed, 10 skipped, six subtests, 25.22 seconds. Log: `/tmp/backend-clock-fix-ci.log`. An initial local command omitted CI's two database-script exclusions and was explicitly interrupted after setup failures (685 failures, 37 passes); process 43298 is terminal, not acceptance evidence. Corrected process 84412 is terminal success. Do not restart the still-running GitHub contention job or publish feature changes while this gate is unresolved. Publish the isolated test repair after that job terminates.

Unpublished document interface work: `ContractDocuments.tsx`, `contract-documents.ts`, integration in `ContractDraft.tsx`, structural file matching in `evidence.ts`, and new helper/component tests. The existing saved-draft step now presents document type, original file, source note, one save/retry action and retained history. Recovery binds user/workspace/property/offer/contract/version and holds parent navigation. Unknown results retain exact metadata and require the original bytes; no preview, signature or review approval is granted. Tests: existing frontend suite 584 passed; new helper tests four passed and component tests ten passed. Typecheck/build passed; lint baseline passed before the new test files. Visual QA and final lint/build after new tests remain pending. First registration rejections currently remain held for administrator reconciliation; a safe explicit-rejection release is not yet implemented. Do not ship this interface as a completed document review process.

Next: complete the isolated CI repair publication; finish document UI visual/reload/navigation QA and explicit rejection recovery, then scan/review bindings, immutable terms/transitions and disposition. No production migration, deployment, upload flag, provider, outreach or fulfillment activation occurred.

## Guided document discovery candidate

Migration 61 and the version-scoped GET documents endpoint provide bounded ordered metadata and currently reviewed retention-policy choices, without raw provenance, private file paths, download URLs or approval authority. Exact workspace/contract/version/purpose, fresh state, pagination and server-owned upload availability are validated. Missing or expired policies remain unavailable; retained revoked/expired history remains visible while activation is paused.

Three focused SQL cases passed in 12.875 seconds, including preservation of populated artifacts/audits. 167 focused API/transport tests and 770 broader contract/evidence regressions passed (9.97 seconds for the broader suite). Full rehearsal process 83996 exited 0: 61 migrations / 26 access probes / 112 workflows / 66 actual gateway checks. Real API discovery verified policy choices, cursor continuity, retained revoked state and tenant/version denial. Evidence: evidence/2026-10-31-contract-discovery-gateway-result.json. All local processes terminal.

Next: integrate these capabilities into the existing saved-contract step with exact pending-file recovery and navigation holds, then finish signed scan/review bindings, immutable terms/transitions and disposition. Do not label uploaded documents reviewed or expose private file previews. Publish only after all six predecessor jobs succeed; hosted Auth/Storage/provider acceptance remains pending.

## Contract binary upload endpoint candidate

The version-scoped document `/bytes` route is implemented behind its own default-closed `ACQUISITION_CONTRACT_UPLOAD_ENABLED` gate. It shares lazy bounded request validation with mail, reserves capacity before input reads, and validates exact contract/version/artifact/purpose and fresh strict receipts. Unknown outcomes preserve the same artifact and file; capacity replies carry Retry-After. Uploaded bytes remain unscanned, unpersisted as verification and legally unapproved. No runtime flag was enabled.

750 contract/evidence tests passed in 9.20 seconds. Full rehearsal process 67621 exited 0: 60 migrations, 26 access probes, 109 workflows and 64 actual gateway checks. Mounted API-to-real-registry/RLS tests verified default closure, tenant denial, committed upload followed by lost/unavailable response, bounded retry recovery without duplicate object, bad-file rejection and revocation during verification. Storage bytes remain synthetic, and hosted Storage/Auth acceptance is unverified. Evidence: evidence/2026-10-31-contract-upload-api-gateway-result.json. All local processes terminal.

Next: publish after all six predecessor checks succeed; add document discovery/policy choices, scan and review bindings, and the guided contract-document flow. Retain workspace/property/draft context, show one next action, and distinguish uploaded documents from completed review. Contract transitions, disposition, closing and remaining PRD gates are still incomplete.

## Contract Storage permission candidate

CLI-created migration 60 adds exact contract-version dispatch to the existing private Storage helper. A contract write requires a current draft, its creator, an active reservation for the exact artifact/version and current workspace/session/retention authority. Mail dispatch, private reads and restrictive no-list/no-replace/no-delete rules are preserved. The separately gated upload endpoint candidate is described above; no production DDL was applied.

Six focused tests passed in process 10837 (26.285 seconds), including real registry/RLS with synthetic Storage bytes and lost-reply recovery. Full rehearsal process 3555 exited 0: 60 migrations, 26 access probes, 107 workflows and 64 actual gateway checks. All seven new workflows passed, including fresh session/member revocation after admission. Evidence: evidence/2026-10-31-contract-storage-gateway-result.json. All local processes terminal. GitHub predecessor 173684f / 41250516262 attempt 1 ended cancelled: five jobs succeeded, full schema job 124682889328 exhausted the 15-minute job limit during slow LLVM/runtime downloads before tests began. Confirmed terminal, inspected logs, and reran only that job on the same commit (attempt 2). Track that retry; do not restart it while live. Continue the all-six publication gate.

Next: publish after the predecessor gate clears, continue document discovery, scan/review bindings and the guided document step. Hosted Storage acceptance remains unverified.

## Internal contract upload transport candidate

Strict contract admission receipts and the shared process semaphore now guard the internal contract upload entry point. Mail and contracts reuse one bounded non-overwriting upload engine, with source-size/hash/type checks, current registry reads and independent authenticated byte reconciliation. Contract receipts retain the exact version and report unpersisted verification, unscanned bytes and no legal/execution approval. No contract HTTP upload route is enabled. The subsequent local Storage permission candidate is described above.

700 contract/evidence API, schema, admission, byte, upload, scan, persistence and journal tests passed in 7.53 seconds. Full shared-path rehearsal process 29868 exited 0: 59 migrations, 26 access probes, 100 workflows, 64 real gateway checks. Evidence: evidence/2026-10-31-contract-shared-upload-gateway-result.json. All local processes are terminal. Next: complete the Storage candidate acceptance above before mounting a contract upload endpoint.

## Shared contract upload admission candidate

Migration 59 extends the existing private upload reservations across mail and contract-version targets, preserving two workspace slots and one active slot per actor. Both RPCs share the same lock and clear the alternate target when expired slots are reused. Current role/session/activation/retention and exact draft/version/creator checks run after waiting. Storage contract uploads remain denied; admission is not upload or review authority.

Thirteen focused database tests passed (process 25764, 57.341 seconds), including populated mail-slot preservation, mixed concurrent capacity, bidirectional reuse, raw privilege denial and observed session/member/policy changes during lock waits. Full rehearsal process 5656 exited 0: 59 migrations, 26 access probes, 100 workflows, 64 actual gateway checks. Evidence: evidence/2026-10-31-contract-upload-gateway-result.json. All local processes are terminal. The first focused run found a fixture attempting an immutable draft mutation; the corrected test verifies that rejection. No production change.

Next: strict contract admission receipts, shared bounded process transport, guarded Storage dispatch and upload reconciliation, signed scan/review binding, then guided document UI. Preserve all-six predecessor CI gate before publication.

## Current contract candidate

Contract draft migration/API passed the full rehearsal: 57 migrations, 26 access probes, 88 full-catalog workflows and 54 local gateway checks. Process 55084 exited 0; evidence/2026-10-31-contract-seller-gateway-result.json. Actual contract API commit-loss recovery, one version/audit, tenant/anonymous isolation and expired-session rejection passed. Contract API/auth regressions (483) and three observed lock-wait cases passed separately.

Added bounded seller-choice API scoped to workspace/lead/property, showing reported names without title claims. Its unit/router/rules suite passed 100 tests; the canonical seller-name join and property isolation now pass the actual local gateway. The guided fifth draft step carries the selected proposal/property, shows existing drafts, preserves an exact uncertain request across reload, and locks workspace/proposal navigation during recovery. An explicit first-attempt database rejection can release the hold; a later rejection never clears an earlier uncertain save. Contract evidence/transitions and all later PRD gates remain incomplete. Frontend regression: 583 tests passed across 73 files, followed by 13 targeted tests including an additional navigation-lock case; 109 contract API/rules tests passed after adding explicit date-only source precision and held forward-review semantics. Typecheck/build passed; lint baseline passed after replacing a control-character regex. Synthetic desktop/mobile browser QA for the fifth step passed, including lost reply, reload, exact recovery and saved-draft reload; screenshots/results are in evidence/contract-draft-2026-10-31. Hosted acceptance is not established. No local process remains running.

## Contract document transport follow-up

Internal contract document descriptors now bind workspace, canonical contract ID/version and purpose. They share the existing bounded private byte-verification transport without changing mail scope or returning execution/legal approval. Focused mail/contract byte/scan/upload tests passed 222; additional evidence API/admission/attestation/journal/persistence and contract regressions passed 344. Actual shared-path gateway rehearsal 80922 exited 0; evidence/2026-10-31-shared-evidence-gateway-result.json contains the exact successful result. The next local registry candidate is described below; document uploads/review endpoints and legal transitions remain incomplete. See CONTRACT-DOCUMENT-PERSISTENCE.md for the exact dependency and acceptance map.

## Contract document registry/API candidate

CLI-created migration 20261031224723 extends the existing evidence registry with mutually exclusive campaign/contract-version targets and authenticated registration/revocation/state RPCs. Existing mail records and private Storage controls are preserved. Contract uploads remain denied. Eight focused SQL cases passed, including populated mail preservation and observed wait-time authority changes. Full candidate rehearsal: 58 migrations, 26 access probes, 95 workflows, 58 actual local gateway checks; evidence/2026-10-31-contract-registry-gateway-result.json. Typed current-registry-before/after byte verification passed synthetic-stream regressions (582 related tests), with a separate store-forwarding check. Hosted and combined real Storage verification remain unproven. No local process remains active. Registry and metadata API are published in 173684f; its exact successor CI is pending.

## Metadata API acceptance

Mounted `/contracts/{contract_id}/versions/{contract_version}/documents` routes register metadata, read current unavailable/held states and revoke records through the existing user-JWT store. Exact path scope, strict unconfirmed receipts and current timestamps are checked; stale/wrong-version replies and claimed approval are rejected. There are no document upload/download/signing/approval routes. 259 focused tests and 681 broader API/auth/evidence regressions passed. Actual mounted API-to-PostgREST registration/revocation lost-response recovery, immutable audits and scope denial passed in process 51089: 58 migrations, 26 access probes, 95 workflows, 62 gateway checks. Evidence: evidence/2026-10-31-contract-document-api-gateway-result.json. All local processes are terminal; no production/hosted acceptance is implied.

## Verified local scope

| Evidence | Latest verified result | Boundary |
| --- | --- | --- |
| Full schema and application rehearsal | 58 additive candidate migrations; 26 access probes; 95 application workflows; 62 real local PostgREST checks | Synthetic records and bot responses; no hosted Auth/provider acceptance |
| Historical compatibility | 24 historical records preserved across 22 populated tables; 103 historical definitions checked | Disposable production-derived catalog, not a production migration |
| Portal/backend regression | 220 portal, authentication and webhook tests passed | Targeted suite; not a newly run whole-backend suite |
| New seller interface | 14 contract/component/journey tests passed; typecheck/build passed | Fake verification widget in tests |
| Interface lint | Zero new findings; 147 existing findings | Existing findings remain |
| Browser QA | Desktop and 375×812 phone flow, lost response/reload/retry, preference disclosure and unavailable form passed; no phone horizontal overflow observed | Built app with local synthetic API and fake widget; browser/server closed afterward |

Evidence: `evidence/2026-10-31-portal-receiver-result.json`, `evidence/seller-portal-2026-10-31/result.json`, corresponding screenshots, and newest PROGRESS.md entries. Older narrower counts are historical, not the current acceptance record.

The portal is disabled by default. Its receiver uses restricted server credentials only for three reviewed RPCs, fresh capacity/verification binding, minimal receipt responses and exact inquiry recovery. `/offer/:formKey` uses four guided seller steps and reviewed form wording. No estimated price or binding offer is displayed. Address input shape is checked; authoritative property/address verification remains a gap.

## One app process

`frontend/src/pages/AcquisitionReview.tsx` now provides five numbered review sections: prepare campaigns, review inquiries, evaluate property, review proposed amount, and prepare a contract draft. `CampaignDrafts.tsx` embeds mail templates, response destinations, content review and supporting files within campaign preparation. The internal mail step numbers are not the overall acquisition phase gates. Preserve the navy/orange styling, workspace/property context and exact pending requests through handoffs.

User-required acceptance standard for every app-facing increment:

- Preserve the existing navy/orange palette, numbered sections, consistent cards, spacing, labels and button hierarchy.
- Keep campaign, seller and property context through each handoff; reuse saved records instead of requiring duplicate entry.
- Show what is complete, what needs attention and one clear primary next action. Explain unavailable actions in plain language.
- Keep detailed evidence and technical identifiers out of the primary flow; expose relevant supporting details progressively.
- Distinguish saved drafts, review decisions, approved execution and completed delivery. A completed screen must not imply a live release gate passed.
- Extend this journey for contracts, disposition and closing when implemented; preserve the PRD's separate channel activation order.
- Verify new screens and transitions together, including loading, empty, error, pending-save and restricted-access states, before claiming usability acceptance.

Amount approval is internal review only. Saving a document or scan observation does not approve evidence or authorize fulfillment. Later contract/disposition screens must extend this same journey with clear next actions; do not present the current four sections as a completed acquisition/closing pipeline.

## Current coverage and gaps

| PRD area | Current source evidence | Required next evidence or implementation |
| --- | --- | --- |
| MIG-001–005 shared foundation | Additive acquisition migrations, SCHEMA-MAPPING.md, workspace/role/session RPCs, suppressions, immutable audit and provider idempotency; standalone workspace and workflow harnesses | Full-catalog upgrade passed 56 candidate migrations, 26 access probes, 82 workflows and 49 local PostgREST checks. Retained features remain local pending repair CI. Hosted Auth issuance, Storage/platform parity and approved deployment remain unverified. Obtain migration approval before production application. |
| FB-001–006 | acquisition_webhooks.py, acquisition_facebook_worker.py, acquisition_intake.py; signed batch inbox, leased retrieval, identity/qualification, recovery, attribution and costs; synthetic database journeys | Disabled supervised runner is published; current Meta permissions/version/subscription and credential custody acceptance, deployed supervision/alerts and monitored retention, approved fresh lead through actual provider and actual auth. No publishing or funding authority. |
| RET-001–006 | acquisition_inbound_webhooks.py, acquisition_inbound_tools.py, inbound intake/restriction/request-review migrations, config/acquisition/inbound draft package | Actual inbound-only Twilio/Retell configuration, approved disclosure/privacy/recording controls, audio/interruption/transfer QA and bilingual acceptance. Draft package and synthetic requests are not live calls. |
| MAIL-001–006 | acquisition_mail.py preparation rules, acquisition_mail_render.py/proof.py, campaign/template/destination/content review UI and SQL | Canonical postal eligibility and suppression matching, authoritative history and locked budget/cadence reservations, persisted batches/jobs, selected vendor adapter and sandbox/proof reconciliation, separately approved fulfillment. Preparation is not a reservation. |
| Evidence supporting mail review | Registry/discovery/upload UI; same-byte scanner; signed ledger/journal; sticky detection hold; locked exact evidence-to-review binding and guided file/deadline selection | Actual worker lifecycle and persistent-volume acceptance, reviewed quarantine clearance, key/scanner deployment, hosted Storage/JWT acceptance, retention administration/holds/purge and additional expiry/revocation contention. Actual local approval gateway coverage passed in the retained increment; it does not prove hosted acceptance. |
| WEB-001–006 and proposed-batch scheduling | Immutable form registry/publication selection; private admission and verification binding; bounded disabled receiver; four-step seller page and exact recovery; real local save/recovery/tenant journeys and synthetic browser QA | Authoritative address verification; hosted proxy identity, key custody, cleanup/retention, actual challenge and approved form acceptance; daily proposed batches and fulfillment reconciliation. See ONLINE-OFFER-PORTAL.md. The local implementation is not a deployed portal. |
| Eligibility | Shared decision ledger and restrictions, channel/purpose distinctions and current blocked/review-only behavior | Counsel-approved principal/assignment policy, applicable DNC/time-zone rules and execution-time rechecks in each live sender. Tests with synthetic ALLOW are not permission. |
| CALL-001–008 and AGENCY-001–006 | acquisition_caller/agency_manager roles and assigned-lead access restrictions exist | Human manual click-to-call queue, fresh execution eligibility, disposition/follow-up/productivity workflow, agency cohorts/suspension/training and controlled pilot. Role names alone do not implement these phases. |
| UW-001–008 | Four-strategy Decimal engine, provenance-bearing three-case inputs, immutable stored results, proposal limits and human internal review; all four persisted paths now tested | Live market/provenance quality and full UI/provider acceptance; approved written-offer template and delivery authorization. No binding offer is sent by amount approval. |
| DISP-001–010 | Shared property/owner/offer foundations; local pure lifecycle/evidence reviewer with 54 tests (CONTRACTS-AND-DISPOSITION.md), no persisted transitions | Executed-contract state machine, title and assignment review, deadlines/deposits, distinct direct-close/assignment paths, buyer profiles/matching, accurate buyer package, required disclosures, approvals and closing reconciliation. No reviewed acquisition disposition implementation was found in the inspected acquisition API/tool/migration paths. |

## Next work in order

1. Complete the merged-candidate validation and publication sequence above. Do not push retained features while predecessor checks fail or remain live.
2. Close shared-foundation and Facebook release acceptance gaps against the complete candidate. Prepare a concrete, reviewable migration/provider acceptance packet before requesting any production or live-test authorization. Portal/mail work does not satisfy the Phase 1 gate.
3. Continue authoritative property/postal verification, suppression/budget/cadence integration, persisted proposed mail batches and vendor reconciliation. PropStream is the existing verification/skip-trace source; no mail vendor is selected. No purchases or provider activation are authorized.
4. Complete remaining inbound/human-caller/agency, contracts/disposition and underwriting-delivery requirements shown above, preserving one guided app process and sequential activation gates.

See [PHASE-1-RELEASE-PACKET.md](PHASE-1-RELEASE-PACKET.md), [ONLINE-OFFER-PORTAL.md](ONLINE-OFFER-PORTAL.md), [POSTAL-AND-BATCH-IMPLEMENTATION.md](POSTAL-AND-BATCH-IMPLEMENTATION.md), and [UPGRADE-REHEARSAL.md](UPGRADE-REHEARSAL.md). Read current source/Git/CI before relying on any older checkpoint in those documents.
