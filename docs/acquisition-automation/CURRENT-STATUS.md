# Acquisition automation — current implementation and release handoff

Updated October 29, 2026 (America/Chicago). This is a navigation and gap inventory based on the current source, not a completion certification. The original PRD and IMPLEMENTATION-PLAN.md remain controlling. Older sections in feature documents are chronological checkpoints; do not interpret an old “next” list as current implementation state.

## Git and validation

- Local branch: codex/acquisition-foundation. Retained feature bce25b9 adds bounded signed-observation persistence; merge 08c859a incorporates the separately pushed CI correction; e6d9b87 adds four-strategy persisted workflow coverage.
- Publication prerequisite: f5491ea124480cca37c49b9a9b800159c1c10a51, run 40998774727. Four jobs passed; PostgreSQL contention is still running at the latest check. Local commits 6be42c1 and e98ee35 add full-catalog access and application journeys. A sixth matching-runtime CI job is prepared; after publishing require all six jobs to pass on the new head.
- Local evidence: 728 evidence/API checks and 48 application-to-PostgreSQL workflows passed. These use isolated databases and synthetic transport/provider evidence. They do not establish live JWT, provider, deployment or operational acceptance.
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
| MIG-001–005 shared foundation | Additive acquisition migrations, SCHEMA-MAPPING.md, workspace/role/session RPCs, suppressions, immutable audit and provider idempotency; standalone workspace and workflow harnesses | Local full-catalog populated upgrade passed all 45 candidate migrations. 19 SQL role/isolation probes now pass on that upgraded baseline; eight application journeys now pass on full-schema copies; add matching hosted rehearsal and real authentication/Data API acceptance; obtain migration approval before deployment. Focused fixtures do not prove this full gate. |
| FB-001–006 | acquisition_webhooks.py, acquisition_facebook_worker.py, acquisition_intake.py; signed batch inbox, leased retrieval, identity/qualification, recovery, attribution and costs; synthetic database journeys | Current Meta permissions/version/subscription and credential custody acceptance, monitored worker/retention, approved fresh lead through actual provider and actual auth. No publishing or funding authority. |
| RET-001–006 | acquisition_inbound_webhooks.py, acquisition_inbound_tools.py, inbound intake/restriction/request-review migrations, config/acquisition/inbound draft package | Actual inbound-only Twilio/Retell configuration, approved disclosure/privacy/recording controls, audio/interruption/transfer QA and bilingual acceptance. Draft package and synthetic requests are not live calls. |
| MAIL-001–006 | acquisition_mail.py preparation rules, acquisition_mail_render.py/proof.py, campaign/template/destination/content review UI and SQL | Canonical postal eligibility and suppression matching, authoritative history and locked budget/cadence reservations, persisted batches/jobs, selected vendor adapter and sandbox/proof reconciliation, separately approved fulfillment. Preparation is not a reservation. |
| Evidence supporting mail review | Registry/discovery/upload UI; same-byte scanner; signed immutable observation ledger and bounded persistence transport | Durable worker request recovery, current quarantine/clearance state, locked evidence-to-review binding, reviewed key/scanner deployment, real Storage/JWT acceptance, retention administration/holds/purge. Legacy evidence-reference fields are not a finished guided file-review integration. |
| WEB-001–006 and proposed-batch scheduling | Campaign channel values and shared intake/underwriting infrastructure exist | Seller-facing portal, authority/consent version capture, privacy/rate/bot controls and review-only pricing; daily proposed batches with reconciliation. An online_offer enum is not a portal. |
| Eligibility | Shared decision ledger and restrictions, channel/purpose distinctions and current blocked/review-only behavior | Counsel-approved principal/assignment policy, applicable DNC/time-zone rules and execution-time rechecks in each live sender. Tests with synthetic ALLOW are not permission. |
| CALL-001–008 and AGENCY-001–006 | acquisition_caller/agency_manager roles and assigned-lead access restrictions exist | Human manual click-to-call queue, fresh execution eligibility, disposition/follow-up/productivity workflow, agency cohorts/suspension/training and controlled pilot. Role names alone do not implement these phases. |
| UW-001–008 | Four-strategy Decimal engine, provenance-bearing three-case inputs, immutable stored results, proposal limits and human internal review; all four persisted paths now tested | Live market/provenance quality and full UI/provider acceptance; approved written-offer template and delivery authorization. No binding offer is sent by amount approval. |
| DISP-001–010 | Shared property/owner/offer foundations | Executed-contract state machine, title and assignment review, deadlines/deposits, distinct direct-close/assignment paths, buyer profiles/matching, accurate buyer package, required disclosures, approvals and closing reconciliation. No reviewed acquisition disposition implementation was found in the inspected acquisition API/tool/migration paths. |

## Next work in order

1. Finish exact prerequisite CI 40998774727, then publish the retained access/workflow/full-rehearsal-CI increments. Inspect the new six-job run before another feature push. Never cancel an active run or disable checks to make this gate appear complete.
2. Close the shared-foundation and Facebook acceptance gaps against the complete candidate. Assemble a concrete migration/provider acceptance packet before requesting production or live-test authorization. Later mail-document work must not be mistaken for completion of the Phase 1 release gate.
3. Complete the mail evidence worker and review binding, canonical mailing rules/reservations, vendor sandbox workflow, and inbound provider acceptance. Keep them within the existing campaign/review screens.
4. Deliver portal, manual human caller, agency and contract/disposition capabilities with the PRD's sequential activation gates. These are still required parts of the goal, not optional enhancements.

PROGRESS.md records detailed checkpoints and test results. CI-RUNTIME-RECOVERY.md records the timeout diagnosis. WORKFLOW-ACCEPTANCE.md describes synthetic test boundaries. No production, provider, spending, outreach, mail, or binding transaction change is made by this status page.

Current upgrade-baseline work: [UPGRADE-REHEARSAL.md](UPGRADE-REHEARSAL.md) documents a fresh catalog capture, stale-baseline differences and the exact next restoration/upgrade checks. Capture and exact application-catalog restoration passed locally, including five negative security/integrity probes. All 45 candidate migrations passed a populated local rehearsal, preserving 24 synthetic historical records and disabled execution controls. 19 full-baseline SQL access probes now pass with all test mutations rolled back. Eight selected application journeys now pass on full-schema copies. Matching hosted rehearsal and managed-platform acceptance remain outstanding.
