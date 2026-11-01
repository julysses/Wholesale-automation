# Remaining acquisition implementation — November 1 checkpoint

This is a next-action map, not a completion claim. The full PRD and activation order remain controlling. CURRENT-STATUS.md records the exact active batch/process and release gate.

## Published buyer preparation and current evidence increment

Scoped buyer storage, immutable profiles, bounded discovery, mounted API and the numbered profile editor are published at90f9c324ef4ccd4c30dae0f8fcbe1a4ed74680e5. Exact successor run41310833331 has all six jobs completed successfully. See CURRENT-STATUS.md for publication of the next batch.

Final118 rehearsal19435 passed376 workflows,26 access probes and175 actual gateway checks. Backend4746 passed/10 skipped; frontend1107 plus53 affected copy tests passed; build/lint and desktop/phone recovery passed. See evidence/2026-11-01-buyer-118-publish-result.json and BUYER-PROFILES.md. This implements owner/admin preparation of self-reported profiles, not buyer verification or selection.

Local119 extends the existing evidence registry and revocation ledger to exact buyer revisions, restricts buyer metadata to owner/admin MFA and blocks buyer files through generic Storage paths. Focused privacy checks and full119 passed377 workflows,26 access probes and175 gateway checks; evidence is recorded in CURRENT-STATUS.md. No dedicated buyer upload, verification, review or matching workflow is available yet. NEXT-BUYER-VERIFICATION.md specifies the next complete workflow.

## Next code work: workspace-scoped buyer selection and disposition

PRD DISP-004–010 and the remaining lifecycle stages are not fulfilled by a purchase-path proposal or a disposition-review handoff.

Reuse the existing canonical `buyers`, `buyer_preferences`, `buyer_transactions`, `deal_matches`, and `buyer_outreach_log` entities. SCHEMA-MAPPING.md records the previous inventory and conflicts. Re-inventory current columns, unique constraints, FKs, grants, policies and service-client paths on the next disposable schema before writing SQL. Do not automatically move historical buyers into a workspace or create a disconnected buyer_profiles clone.

Concrete source boundary: `web/api/buyers_api.py` uses `_get_supabase()` for import, scoring, leaderboard, matching, SMS/email outreach, transaction history, classification and import deletion; these routes currently have no workspace selector. `tools/buyer_intelligence_engine.py` supplies reusable matching/scoring. `schemas/buyer.py` already defines buy boxes/strategies. Published116–118 now contain these legacy service-client paths and child/cascade operations as well as RLS. Maintain that boundary when implementing controlled matching and transactions. Preserve legacy behavior for legacy rows while denying acquisition-scoped records through unscoped routes. Existing role names alone do not establish assigned caller/agency authorization.

UI integration inspection: `frontend/src/pages/Buyers.tsx` currently exposes “Blast New Deal”; `useBuyers.ts` directly reads/writes the global table and keys its cache without workspace. `Reports.tsx`, `LandBuyerHub.tsx`, `DealHandoffFields.tsx`, and `BuyerIntelligence.tsx` also read buyer or outreach data directly. Account for all of these surfaces before scoped rows become readable. In the acquisition contract flow, place selection after the reviewed purchase path and disposition handoff, with numbered choose/review/confirm steps and matching navy/orange controls. A buyer score or “POF verified” legacy flag must not become acquisition approval evidence. Keep exact pending-request recovery visible and block navigation that could discard an uncertain save.

Historical pre-change disposable115 inventory is saved in `evidence/2026-11-01-buyer-local-catalog.json` (session68381 terminal0). At that inventory checkpoint buyer tables had no workspace column; restrictive legacy-access policies coexist with permissive legacy policies. `deal_matches` and `buyer_outreach_log` have restrictive deal-based access but buyer-only outreach is not buyer-scoped. Incoming links also include `deals.buyer_id` and `tasks.buyer_id`, so guarding only buyer child tables is insufficient. Existing acquisition tasks have a shape constraint limited to inbound callback/human-review tasks with buyer_id NULL; do not repurpose that shape silently.

Database surfaces include `buyer_leaderboard`, `ibie_segment_summary`, and `reportable_deals`, plus `record_sendgrid_events`. Preserve trusted one-way suppression updates: that receiver sets email_opt_in=false across matching buyer emails and must not accidentally permit broader scoped mutations or lose opt-out propagation. Verify view security options/owners/grants as well as row policies before exposing scoped buyers. The completed inventory rerun21661 (terminal0; `/tmp/buyer-catalog-115-authority.log`) captures definitions, owners, ACLs and view options. All three views use security_invoker=true. The two buyer views retain broad legacy grants to anon/authenticated/service_role; service-role requests bypass RLS, so invoker mode alone does not isolate their results. Published116–118 explicitly exclude scoped rows from buyer-specific legacy views and filter legacy service-client reads; preserve those boundaries as new scoped projections are added. Existing `record_sendgrid_events` is an invoker routine granted only to service_role/postgres; preserve its trusted one-way suppression purpose.

Implement in this order:

1. Complete individually reviewed buyer evidence and verification beside the published bounded owner/admin discovery and buy-box maintenance. No bulk export or automatic outreach.
2. Explainable investor matching against the reviewed contractual opportunity, with verification/currentness and closing-capability evidence. An existing score is not proof of financing or eligibility.
3. A reviewable buyer package accurately describing Hilltop's contractual interest. Version the exact package and source evidence; human review must precede distribution. Counsel-approved seller/assignee disclosure evidence and legally reviewed assignment permission must be enforced, not inferred from a checkbox or generic template.
4. Separate controlled principal purchase and assignment paths, with approved agreement/closing-structure decisions, buyer deposit, milestones, gross fee, expenses and net proceeds. Preserve the canonical deal and immutable transition history.
5. Controlled `assigned_or_direct_close`, `closed`, `cancelled`, `expired`, and `disputed` states. Preserve legacy pipeline semantics; do not fabricate an assignee or assignment document for a principal purchase. Retain exact recovery and exception audit trails.

Each increment needs bounded authenticated API projections, existing step-by-step UI placement, actual isolation/idempotency/concurrency tests, and desktop/phone acceptance where UI changes. Do not activate legacy buyer blast endpoints as a shortcut.

## Channel gates still require environment-specific acceptance

- Phase1 Facebook: use PHASE-1-RELEASE-PACKET.md and current implementation evidence. Reverify approved Meta configuration/API and credentials at activation time; use approved fresh test leads. Prove complete attribution and unchanged paused SMS schedules. No campaign publishing or funding is authorized by local tests.
- Phase2 inbound voice: use INBOUND-VOICE.md. Actual Twilio/Retell routing, provider authenticity, AI identification, recording/transcription controls, interruptions/human escalation and bilingual QA require their own evidence. No outbound AI voice permission is inferred.
- Phase2/3 mail: PropStream is the user's verification/skip-trace provider; no letter/postcard vendor was selected. Complete adapter/sandbox/proof/reconciliation and separately approved fulfillment. Templates, evidence, previews and proposed batches are not mail orders.
- Phase3 online offers: retain request-an-offer defaults, private underwriting, consent versions, abuse controls and human offer approval. Complete hosted end-to-end acceptance before enabling public intake or estimated pricing.
- Phase4/5 human callers/agencies: complete assigned queues, one-action/one-call server-side fresh eligibility, dispositions/tasks, limited access, productivity/quality metrics, agency suspension/revocation and controlled pilot. Counsel approval and reviewed practices remain prerequisites for live outbound calling.

## Release boundaries

No production migration, provider activation, outreach, funded advertising, fulfillment, binding offer, assignment or closing is authorized merely by a green build, synthetic proof, or UI checklist. Keep the existing CRM/county workflows and paused SMS recovery intact. Complete the shared foundation before sequential channel activation. Preserve the full goal until the original numbered requirements and release gates have authoritative evidence.
