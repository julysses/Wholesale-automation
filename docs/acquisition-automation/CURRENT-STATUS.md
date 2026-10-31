# Acquisition automation — current implementation and release handoff

Updated October 31, 2026 (America/Chicago). The original PRD and IMPLEMENTATION-PLAN.md remain controlling. This page is current scope/status; chronological results and commands are in PROGRESS.md. Nothing here certifies production or provider acceptance.

## Publication and active process

- Published candidate: `c935460b8b05c12b5247382012a463ddc4ffa3c8` on `codex/acquisition-foundation`. Normal push confirmed `bbcec81` → `c935460`; checkout was clean. Exact successor CI `41249648671` is queued: https://github.com/julysses/Wholesale-automation/actions/runs/41249648671. Require all six terminal successes before the next feature push. Predecessor `bbcec81` / CI `41248426556` passed all six.
- Predecessor `5ca649c` / CI `41246949570` completed successfully with all six jobs. Prior fixture repair `2f2dbe7` / CI `41245920319` also passed all six. No jobs cancelled or restarted.
- Contract draft schema/API/rules and seller choices are published in Git, not deployed. The fifth guided draft step is published in Git; synthetic desktop/mobile browser QA passed. Shared evidence regression rehearsal 80922 exited 0: 57 migrations, 26 access probes, 88 workflows, 54 gateway checks. No local test or preview process is active.
- Branch automatic deployment is disabled. No production migration, provider setting, spend, outreach, fulfillment or binding transaction was performed. Preserve paused SMS and existing county/CRM behavior.

## Current contract candidate

Contract draft migration/API passed the full rehearsal: 57 migrations, 26 access probes, 88 full-catalog workflows and 54 local gateway checks. Process 55084 exited 0; evidence/2026-10-31-contract-seller-gateway-result.json. Actual contract API commit-loss recovery, one version/audit, tenant/anonymous isolation and expired-session rejection passed. Contract API/auth regressions (483) and three observed lock-wait cases passed separately.

Added bounded seller-choice API scoped to workspace/lead/property, showing reported names without title claims. Its unit/router/rules suite passed 100 tests; the canonical seller-name join and property isolation now pass the actual local gateway. The guided fifth draft step carries the selected proposal/property, shows existing drafts, preserves an exact uncertain request across reload, and locks workspace/proposal navigation during recovery. An explicit first-attempt database rejection can release the hold; a later rejection never clears an earlier uncertain save. Contract evidence/transitions and all later PRD gates remain incomplete. Frontend regression: 583 tests passed across 73 files, followed by 13 targeted tests including an additional navigation-lock case; 109 contract API/rules tests passed after adding explicit date-only source precision and held forward-review semantics. Typecheck/build passed; lint baseline passed after replacing a control-character regex. Synthetic desktop/mobile browser QA for the fifth step passed, including lost reply, reload, exact recovery and saved-draft reload; screenshots/results are in evidence/contract-draft-2026-10-31. Hosted acceptance is not established. No local process remains running.

## Contract document transport follow-up

Internal contract document descriptors now bind workspace, canonical contract ID/version and purpose. They share the existing bounded private byte-verification transport without changing mail scope or returning execution/legal approval. Focused mail/contract byte/scan/upload tests passed 222; additional evidence API/admission/attestation/journal/persistence and contract regressions passed 344. Actual shared-path gateway rehearsal 80922 exited 0; evidence/2026-10-31-shared-evidence-gateway-result.json contains the exact successful result. Registry/Storage extensions, document upload/review endpoints and legal transitions are not implemented. See CONTRACT-DOCUMENT-PERSISTENCE.md for the exact dependency and acceptance map.

## Verified local scope

| Evidence | Latest verified result | Boundary |
| --- | --- | --- |
| Full schema and application rehearsal | 57 additive candidate migrations; 26 access probes; 88 application workflows; 54 real local PostgREST checks | Synthetic records and bot responses; no hosted Auth/provider acceptance |
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
