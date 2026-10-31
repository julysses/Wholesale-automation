# Acquisition automation — current implementation and release handoff

Updated October 30, 2026 (America/Chicago). This is a navigation and gap inventory based on the current source, not a completion certification. The original PRD and IMPLEMENTATION-PLAN.md remain controlling. Older sections in feature documents are chronological checkpoints; do not interpret an old “next” list as current implementation state.

## Latest handoff

Published head 320e405 patches follow-redirects to 1.16.2 after the previous registry run failed only its dependency security audit. Local audit has zero high/critical findings; frontend tests/build/lint passed. Exact successor 41234812907 last had five successful jobs and contention in progress. Verify the exact-head successor CI before publishing the retained form API increment. Check PROGRESS.md and live Git/CI before publication.

The disabled form-version registry is published. Form save/history administration API and actual local gateway acceptance are implemented in the retained increment; guided internal setup is now implemented locally; public seller routing/submissions remain required. No hosted process, scheduler, alert destination, provider or production migration was enabled.

## Git and validation

- Branch: codex/acquisition-foundation. Latest all-six prerequisite before the current security repair: 0281b14 / CI 41147496592. Verify security repair 320e405 successor before another feature push.
- Current local rehearsal: 51 additive migrations, 26 access probes, 65 full-catalog workflows and 28 actual local PostgREST checks, including five real form-registry gateway checks. Existing frontend suite: 545 passed including guided form setup; registry/legacy API suite: 98 passed; new administration API boundary suite: 44 passed.
- Hosted CI verifies code and synthetic full-schema rehearsal. It does not verify hosted Supabase Auth issuance, live provider delivery, persistent worker storage or deployment acceptance.
- No production migration or acquisition activation is authorized by these commits. Preserve paused SMS and all existing county/CRM behavior. Older chronological sections below remain historical.

## One app process

`frontend/src/pages/AcquisitionReview.tsx` currently provides four numbered review sections: prepare campaigns, review inquiries, evaluate property, review proposed amount. `CampaignDrafts.tsx` embeds mail templates, response destinations, content review and supporting files within campaign preparation. The internal mail step numbers are not the overall acquisition phase gates. Preserve the navy/orange styling, workspace/property context and exact pending requests through handoffs.

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
| MIG-001–005 shared foundation | Additive acquisition migrations, SCHEMA-MAPPING.md, workspace/role/session RPCs, suppressions, immutable audit and provider idempotency; standalone workspace and workflow harnesses | Full-catalog upgrade passed 51 candidate migrations, 26 access probes and 65 workflows; 28 local PostgREST checks passed. The administration API increment is retained locally pending predecessor CI. Hosted Auth issuance, Storage/platform parity and approved deployment remain unverified. Obtain migration approval before production application. |
| FB-001–006 | acquisition_webhooks.py, acquisition_facebook_worker.py, acquisition_intake.py; signed batch inbox, leased retrieval, identity/qualification, recovery, attribution and costs; synthetic database journeys | Disabled supervised runner is published; current Meta permissions/version/subscription and credential custody acceptance, deployed supervision/alerts and monitored retention, approved fresh lead through actual provider and actual auth. No publishing or funding authority. |
| RET-001–006 | acquisition_inbound_webhooks.py, acquisition_inbound_tools.py, inbound intake/restriction/request-review migrations, config/acquisition/inbound draft package | Actual inbound-only Twilio/Retell configuration, approved disclosure/privacy/recording controls, audio/interruption/transfer QA and bilingual acceptance. Draft package and synthetic requests are not live calls. |
| MAIL-001–006 | acquisition_mail.py preparation rules, acquisition_mail_render.py/proof.py, campaign/template/destination/content review UI and SQL | Canonical postal eligibility and suppression matching, authoritative history and locked budget/cadence reservations, persisted batches/jobs, selected vendor adapter and sandbox/proof reconciliation, separately approved fulfillment. Preparation is not a reservation. |
| Evidence supporting mail review | Registry/discovery/upload UI; same-byte scanner; signed ledger/journal; sticky detection hold; locked exact evidence-to-review binding and guided file/deadline selection | Actual worker lifecycle and persistent-volume acceptance, reviewed quarantine clearance, key/scanner deployment, hosted Storage/JWT acceptance, retention administration/holds/purge and additional expiry/revocation contention. Actual local approval gateway coverage passed in the retained increment; it does not prove hosted acceptance. |
| WEB-001–006 and proposed-batch scheduling | Shared intake/underwriting infrastructure; exact online-offer request/preparer and local immutable form-version registry with workspace/campaign binding and no authority grant | Hosted administration UI/API acceptance, controlled public version routing, transactional intake, public privacy/rate/bot controls and four-step seller UI; hosted end-to-end acceptance; daily proposed batches with reconciliation. See ONLINE-OFFER-PORTAL.md. A contract/preparer is not a deployed portal. |
| Eligibility | Shared decision ledger and restrictions, channel/purpose distinctions and current blocked/review-only behavior | Counsel-approved principal/assignment policy, applicable DNC/time-zone rules and execution-time rechecks in each live sender. Tests with synthetic ALLOW are not permission. |
| CALL-001–008 and AGENCY-001–006 | acquisition_caller/agency_manager roles and assigned-lead access restrictions exist | Human manual click-to-call queue, fresh execution eligibility, disposition/follow-up/productivity workflow, agency cohorts/suspension/training and controlled pilot. Role names alone do not implement these phases. |
| UW-001–008 | Four-strategy Decimal engine, provenance-bearing three-case inputs, immutable stored results, proposal limits and human internal review; all four persisted paths now tested | Live market/provenance quality and full UI/provider acceptance; approved written-offer template and delivery authorization. No binding offer is sent by amount approval. |
| DISP-001–010 | Shared property/owner/offer foundations | Executed-contract state machine, title and assignment review, deadlines/deposits, distinct direct-close/assignment paths, buyer profiles/matching, accurate buyer package, required disclosures, approvals and closing reconciliation. No reviewed acquisition disposition implementation was found in the inspected acquisition API/tool/migration paths. |

See [PHASE-1-RELEASE-PACKET.md](PHASE-1-RELEASE-PACKET.md) for the exact candidate, verified local scope and remaining hosted/provider acceptance before any production proposal.

## Next work in order

1. Verify all six jobs of security repair 320e405 before publishing the retained form-administration API and guided setup. Then inspect its exact-head successor run. Check branch/status and newest PROGRESS.md before resuming.
2. Close the shared-foundation and Facebook acceptance gaps against the complete candidate. Assemble a concrete migration/provider acceptance packet before requesting production or live-test authorization. Later mail-document work must not be mistaken for completion of the Phase 1 release gate.
3. Complete the mail evidence worker and remaining binding acceptance, canonical mailing rules/reservations, vendor sandbox workflow, and inbound provider acceptance. Keep them within the existing campaign/review screens.
4. Deliver portal, manual human caller, agency and contract/disposition capabilities with the PRD's sequential activation gates. These are still required parts of the goal, not optional enhancements.

PROGRESS.md records detailed checkpoints and test results. CI-RUNTIME-RECOVERY.md records the timeout diagnosis. WORKFLOW-ACCEPTANCE.md describes synthetic test boundaries. No production, provider, spending, outreach, mail, or binding transaction change is made by this status page.

Current upgrade-baseline work: [UPGRADE-REHEARSAL.md](UPGRADE-REHEARSAL.md) documents a fresh catalog capture, stale-baseline differences and the exact next restoration/upgrade checks. Capture and exact application-catalog restoration passed locally, including five negative security/integrity probes. All 45 candidate migrations passed a populated local rehearsal, preserving 24 synthetic historical records and disabled execution controls. 19 full-baseline SQL access probes now pass with all test mutations rolled back. All 48 application journeys now pass locally on full-schema copies. The hosted eight-case predecessor rehearsal passed; the expanded run and managed-platform acceptance remain outstanding.


Local transport increment: real PostgREST 16.5 passed six signed-session/tenant/revocation checks on a copy of the fully upgraded database. The new --acquisition-postgrest command and checksum-pinned CI runtime are prepared. Hosted Auth issuance/MFA lifecycle, actual Storage transport and provider acceptance remain open; see UPGRADE-REHEARSAL.md and the saved result for the exact local scope.


Mail continuation: POSTAL-AND-BATCH-IMPLEMENTATION.md records the inspected phone/email-only endpoint gap and concrete postal/batch dependency order. The campaign card now keeps technical IDs expandable and clearly identifies mailing preparation as incomplete until recipient/contact checks and batch approval are implemented. The existing three numbered mail steps are preserved.


Postal provenance foundation: local migration 20261030041400 preserves the owner mailing-address source as an immutable unverified observation tied to existing workspace owner/property relationships. Full upgrade now passes 46 migrations and all 49 workflows, including postal HTTP retry and access checks. Canonical postal validation, suppression integration and an app import action remain pending; this does not authorize mail. See POSTAL-AND-BATCH-IMPLEMENTATION.md.


Postal HTTP checkpoint: signed concurrent import and tenant checks passed locally; a real activation-lock/session-expiry race was reproduced and fixed in the unpublished postal migration. The final full rehearsal passed ten real PostgREST checks, with no extra row/audit after rejected expiry. Canonical postal validation, shared suppression integration and app import UX remain next.


### 2026-10-30 supporting-file status interface — local validation
The existing mail supporting-files step now has an explicit, scoped Check file status action with plain next-step guidance. It reports current scan assessment separately from registration history and never approves file use, content or mailing. Refresh/access failures hide old scan results. 33 related tests, frontend build and lint baseline pass. Publication is held until all six jobs of predecessor CI 41105042913 succeed; five were successful and the contention job was still live at this checkpoint. Locked evidence-to-content approval binding and the remaining original PRD scope are still incomplete.


### 2026-10-30 content-review session race repaired locally
All six predecessor CI checks passed on d1094c3 / 41105042913. Proposed migration 20261030182649 repairs a reproduced session-expiry race in content review without changing its signature or saved history. The final isolated rehearsal passed 48 migrations, 55 application journeys, 26 access probes, historical preservation and 14 real local PostgREST checks. The guided supporting-file UI, actual transport tests and rendered synthetic walkthrough are retained for the next push. Quarantine clearance, locked file-to-approval binding and the broader PRD remain incomplete; nothing is activated in production.


### 2026-10-30 exact evidence binding — backend implemented, UI handoff remains
Proposed migration 20261030214239 binds new content approvals to an exact registered file/hash and current signed scan, serializes alias detections, and invalidates current approval/proof when evidence becomes untrusted. Old unbound reviews remain historical and withdrawable. All 49 proposed migrations, 58 full-catalog journeys, 18 real local gateway checks, the additional alias-contention test and 15 existing mail regressions passed. Predecessor a1b0bad CI 41132959949 is all-six successful. Guided file selection, actual limiting-expiry presentation, clearance and further binding acceptance remain open; this does not activate anything in production.
