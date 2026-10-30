# Acquisition automation — current implementation and release handoff

Updated October 30, 2026 (America/Chicago). This is a navigation and gap inventory based on the current source, not a completion certification. The original PRD and IMPLEMENTATION-PLAN.md remain controlling. Older sections in feature documents are chronological checkpoints; do not interpret an old “next” list as current implementation state.

## Latest handoff

Postal import now has a disabled-by-default API with strict scope, exact retry and unverified receipt checks. Full local rehearsal passed 46 migrations, 26 access checks, 49 application journeys and ten real PostgREST checks; nine malformed-receipt tests passed. No new operator button is exposed until canonical address validation and shared eligibility are implemented. User selected PropStream as the address-data/skip-trace source; letters/postcards provider remains unselected. Prior commit 31cd558 passed all six jobs in run 41003002597. See PROGRESS.md for publication and remaining work.

Current scan assessment is now implemented locally as a scoped read-only RPC/API, with sticky same-byte detection holds and current signer/observer/retention checks. It grants no preview or approval. Final local rehearsal passes 47 migrations and 51 application journeys; locked evidence-to-review binding remains next. Exact prerequisite ee82549 / run 41097350211 passed all six jobs. See the newest PROGRESS.md checkpoint for publication.

## Git and validation

- Branch: codex/acquisition-foundation. Published predecessor 85419cf adds the private signed-observation journal. Retained b320bd5, 477a4f9 and 6fb59e3 add scoped restart discovery, bounded admission and original-destination binding. See the newest PROGRESS.md checkpoint for publication verification.
- Exact prerequisite 85419cfb7873e5e9b96ca5a843b6562717c629e1 / run 41082200037 completed successfully with all six jobs. Publish the retained commits, then verify the successor run before further feature publication.
- Current local evidence: 46 additive migrations, 26 access probes, 49 full-catalog application journeys, ten actual local PostgREST checks, nine postal receipt-boundary checks and a separate 49-case focused workflow run. Guided intake changes passed 34 related frontend tests, typecheck/build and synthetic browser review including access-revocation refresh. Journal/transport recovery now has 103 passing tests, including actual process exit, concurrent admission, compatibility, scope and endpoint binding.
- Hosted CI verifies code and synthetic full-schema rehearsal. It does not verify hosted Supabase Auth issuance, live provider delivery, persistent worker storage or deployment acceptance.
- No production migration or acquisition activation is authorized by these commits. Preserve paused SMS and all existing county/CRM behavior.

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
| MIG-001–005 shared foundation | Additive acquisition migrations, SCHEMA-MAPPING.md, workspace/role/session RPCs, suppressions, immutable audit and provider idempotency; standalone workspace and workflow harnesses | Full-catalog upgrade passed 46 candidate migrations, 26 access probes and 49 application journeys; ten local PostgREST checks passed. The matching hosted full-schema job passed in run 41080189204; the complete run is successful. Hosted Auth issuance, Storage/platform parity and approved deployment remain unverified. Obtain migration approval before production application. |
| FB-001–006 | acquisition_webhooks.py, acquisition_facebook_worker.py, acquisition_intake.py; signed batch inbox, leased retrieval, identity/qualification, recovery, attribution and costs; synthetic database journeys | Current Meta permissions/version/subscription and credential custody acceptance, monitored worker/retention, approved fresh lead through actual provider and actual auth. No publishing or funding authority. |
| RET-001–006 | acquisition_inbound_webhooks.py, acquisition_inbound_tools.py, inbound intake/restriction/request-review migrations, config/acquisition/inbound draft package | Actual inbound-only Twilio/Retell configuration, approved disclosure/privacy/recording controls, audio/interruption/transfer QA and bilingual acceptance. Draft package and synthetic requests are not live calls. |
| MAIL-001–006 | acquisition_mail.py preparation rules, acquisition_mail_render.py/proof.py, campaign/template/destination/content review UI and SQL | Canonical postal eligibility and suppression matching, authoritative history and locked budget/cadence reservations, persisted batches/jobs, selected vendor adapter and sandbox/proof reconciliation, separately approved fulfillment. Preparation is not a reservation. |
| Evidence supporting mail review | Registry/discovery/upload UI; same-byte scanner; signed immutable observation ledger and bounded persistence transport | Durable single-host request journal now exists; actual worker lifecycle and persistent-volume acceptance, current quarantine/clearance state, locked evidence-to-review binding, reviewed key/scanner deployment, real Storage/JWT acceptance, retention administration/holds/purge. Legacy evidence-reference fields are not a finished guided file-review integration. |
| WEB-001–006 and proposed-batch scheduling | Campaign channel values and shared intake/underwriting infrastructure exist | Seller-facing portal, authority/consent version capture, privacy/rate/bot controls and review-only pricing; daily proposed batches with reconciliation. An online_offer enum is not a portal. |
| Eligibility | Shared decision ledger and restrictions, channel/purpose distinctions and current blocked/review-only behavior | Counsel-approved principal/assignment policy, applicable DNC/time-zone rules and execution-time rechecks in each live sender. Tests with synthetic ALLOW are not permission. |
| CALL-001–008 and AGENCY-001–006 | acquisition_caller/agency_manager roles and assigned-lead access restrictions exist | Human manual click-to-call queue, fresh execution eligibility, disposition/follow-up/productivity workflow, agency cohorts/suspension/training and controlled pilot. Role names alone do not implement these phases. |
| UW-001–008 | Four-strategy Decimal engine, provenance-bearing three-case inputs, immutable stored results, proposal limits and human internal review; all four persisted paths now tested | Live market/provenance quality and full UI/provider acceptance; approved written-offer template and delivery authorization. No binding offer is sent by amount approval. |
| DISP-001–010 | Shared property/owner/offer foundations | Executed-contract state machine, title and assignment review, deadlines/deposits, distinct direct-close/assignment paths, buyer profiles/matching, accurate buyer package, required disclosures, approvals and closing reconciliation. No reviewed acquisition disposition implementation was found in the inspected acquisition API/tool/migration paths. |

## Next work in order

1. Exact prerequisite CI 41001242316 passed all six jobs. Publish the retained postal increments and inspect the successor exact-head six-job result before another feature push.
2. Close the shared-foundation and Facebook acceptance gaps against the complete candidate. Assemble a concrete migration/provider acceptance packet before requesting production or live-test authorization. Later mail-document work must not be mistaken for completion of the Phase 1 release gate.
3. Complete the mail evidence worker and review binding, canonical mailing rules/reservations, vendor sandbox workflow, and inbound provider acceptance. Keep them within the existing campaign/review screens.
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
