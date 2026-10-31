# Acquisition automation — current implementation and release handoff

Updated October 31, 2026 (America/Chicago). The original PRD and IMPLEMENTATION-PLAN.md remain controlling. This page is current scope/status; chronological results and commands are in PROGRESS.md. Nothing here certifies production or provider acceptance.

## Publication and active process

- Published merged candidate: `5ca649c0fbcb4247872767b40f71c6717fc5d20b` on `codex/acquisition-foundation`. Normal push confirmed `2f2dbe7` → `5ca649c`. Exact successor CI `41246949570` was queued at the latest observation: https://github.com/julysses/Wholesale-automation/actions/runs/41246949570. Require all six terminal successes before the next feature push.
- Predecessor repair `2f2dbe788e1f090f5888b80d68c95db1d2ac7167` / CI `41245920319` completed with all six jobs successful. It corrects historical-upgrade fixture ordering; both originally failing cases also passed after the merge in 14.718 seconds. Evidence: `evidence/2026-10-31-merged-fixture-result.json` and the published full 217-case repair log.
- The retained disabled admission, verified acceptance, receiver and four-step seller UI are now published in Git. This does not mean deployed or live. The merge preserved the migration 54–56 fixture guard and changed no application/test code relative to the validated retained head. Both documentation histories are retained.
- No local test or preview process remains running. Branch automatic deployment is disabled in vercel.json. No production migration, provider setting, spend, outreach, fulfillment or binding transaction was performed. Preserve paused SMS and existing county/CRM behavior.

## Current local contract candidate

Contract draft migration 57 passed the corrected full rehearsal: 57 migrations, 26 access probes, 88 full-catalog workflows and 49 existing local gateway checks. Process 57913 exited 0; evidence/2026-10-31-contract-drafts-full-result.json. Contract API/auth regressions (483) and three lock-wait cases also passed.

The expanded actual contract API/gateway journey is now running as process 98367, log /tmp/acquisition-contract-api-gateway.log. It adds real commit-loss recovery, one version/audit, tenant/anonymous isolation and expired-session checks. This new gateway coverage is not yet accepted. The guided draft screen and property-specific seller choices are not implemented yet. No hosted/provider/transaction acceptance is implied.

## Verified local scope

| Evidence | Latest verified result | Boundary |
| --- | --- | --- |
| Full schema and application rehearsal | 57 additive candidate migrations; 26 access probes; 88 application workflows; 49 real local PostgREST checks | Synthetic records and bot responses; no hosted Auth/provider acceptance |
| Historical compatibility | 24 historical records preserved across 22 populated tables; 103 historical definitions checked | Disposable production-derived catalog, not a production migration |
| Portal/backend regression | 220 portal, authentication and webhook tests passed | Targeted suite; not a newly run whole-backend suite |
| New seller interface | 14 contract/component/journey tests passed; typecheck/build passed | Fake verification widget in tests |
| Interface lint | Zero new findings; 147 existing findings | Existing findings remain |
| Browser QA | Desktop and 375×812 phone flow, lost response/reload/retry, preference disclosure and unavailable form passed; no phone horizontal overflow observed | Built app with local synthetic API and fake widget; browser/server closed afterward |

Evidence: `evidence/2026-10-31-portal-receiver-result.json`, `evidence/seller-portal-2026-10-31/result.json`, corresponding screenshots, and newest PROGRESS.md entries. Older narrower counts are historical, not the current acceptance record.

The portal is disabled by default. Its receiver uses restricted server credentials only for three reviewed RPCs, fresh capacity/verification binding, minimal receipt responses and exact inquiry recovery. `/offer/:formKey` uses four guided seller steps and reviewed form wording. No estimated price or binding offer is displayed. Address input shape is checked; authoritative property/address verification remains a gap.

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
