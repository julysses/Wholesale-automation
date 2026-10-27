# Acquisition automation — verified schema mapping

Observed October 25, 2026, America/Chicago (catalog checkpoint 2026-10-26 02:31:52 UTC). Status: historical inventory with additive implementation tracked in PROGRESS.md; no production migrations applied.

## Evidence and baseline

Live Supabase project: `dvzhzlipbwzzcliujzyz` (`wholesale-automation`). Catalog evidence: [2026-10-25-catalog.json](evidence/2026-10-25-catalog.json). Metadata was read in separate READ ONLY transactions; this is not a backup or a transactionally consistent snapshot. No seller records, message bodies, credentials or raw provider payloads were exported.

Inventory covers public, private and wholesale_ingest: **103 tables, 17 views, 1,638 columns, 407 constraints, 248 indexes, 127 policies, 28 non-internal triggers and 122 function signatures/security settings**. Policy inventory also checked storage and found no policies there. Storage bucket configuration and application access were not audited. All 103 application tables have RLS enabled; all 17 public views have `security_invoker=true`. Neither observation establishes tenant isolation.

Vercel lookup of `wholesale-automation.vercel.app` identifies production deployment `dpl_3VmD6PS8eWxGYPh5qzVCZ9ouWW5d`, READY, commit **`c8673c170368bc8c44974fd304fac5af3fcf6e8c`**. That exact published commit was fetched and inspected. The returned alias list omits the requested short hostname; a separate alias/HTTP audit is still needed before claiming complete domain routing verification. Latest project deployment is a different preview; it is not the production baseline.

Planning branch `codex/acquisition-prd-v1-plan` began at repository default `ad70c7c`. It is **not an implementation/release candidate**: 58 migration files in production source are absent here. Production source contains 107 migration files versus 49 on this planning branch. The live ledger has 95 entries, including October 23 Retell recovery controls. [Migration comparison](evidence/migration-comparison.json) records exact filenames and ledger correspondence. Three ledger names have no same-name production file: `priority_rank_recompute`, `lead_street_key`, `lead_lists_grants`. Other timestamps differ between local files and ledger entries; matching names do not prove identical SQL bodies. Never replay old migrations to make filenames match.

For implementation, start an isolated branch from the verified deployed revision, carry forward these planning documents, and recheck production for changes. Do not merge this older application tree into production. The published production revision is available; no missing unpublished candidate has been reconstructed.

## Live operational boundaries

- `private.retell_sms_scheduler.enabled=false` and `private.retell_app_scheduler.enabled=false`.
- Cron jobs `wholesaleos-retell-form-sms` and `wholesaleos-retell-app-sms` are inactive.
- `refresh-lead-retention` and `launch-monitor-every-15m` remain active. Do not describe all cron as paused.
- Deployed source still declares `/webhooks/_worker/sms-nurture` in vercel.json. Actual Vercel cron registration and effective deployed environment booleans were not returned by the connector, and were not verified. No workers were invoked.
- Retell/Twilio/Meta provider settings, handset acceptance, current ad state and effective send flags remain unverified in this pass. Database scheduler state alone is not proof that every dispatch path is disabled.

## Critical compatibility findings

**Tenant foundation is absent.** No `workspace_id`, `tenant_id` or `organization_id` columns exist in the three inventoried application schemas. `profiles.role` accepts only `admin` or `user`. `public.is_approved()` checks the current user's approved status, not workspace membership; `private.is_approved_admin()` checks approved admin status. Many permissive policies are narrowed by restrictive `require_approved_operator` policies, so this is not simply anonymous access. It remains a shared approved-operator system and fails the PRD's multi-workspace requirement.

`development_workspaces` is a per-user development-model JSON document, not organizational membership. Reuse auth identities and profiles, but add actual workspaces/memberships and scoped roles; do not mistake the existing name for a tenancy primitive. `web/auth.py` at the deployed revision is explicit about shared approval-based access. It protects `/api/` and `/v1/`, while provider routes enforce separate authentication. The proposed `/internal/outreach/eligibility/evaluate` path requires explicit authentication and workspace authorization; existing path-based middleware alone does not cover it. Service-role CRM clients require server-side checks in addition to RLS.

**Existing identity is split across lead and ingestion records.** Owner/property attributes are denormalized on `public.leads`; canonical Dallas/Collin properties exist in `wholesale_ingest.properties`, with verified `property_aliases`. Properties have a unique lead_id link; contacts link to leads and trace requests. Reusing these IDs requires a compatibility bridge before supporting many intakes per property or many properties per owner. Phone matches are candidates for review, never proof that two properties or owners are identical.

**Existing Facebook safeguards are real but incomplete for this PRD.** `facebook_lead_submissions` has unique leadgen_id and lead_id, immutable receipt triggers, restricted SELECT/INSERT service-role grants, and exact receipt/lead/phone linkage to Retell jobs. Preserve these controls. `tools/facebook_consent.py` separately validates recognized-form SMS and AI-call checkboxes. These are evidence checks, not counsel-approved channel eligibility. `web/api/webhooks.py:1843` verifies signatures but awaits `_process_inline`; `_process_inline:2126` explicitly says it is not a durable worker. `webhook_jobs` has no provider-event unique key. FB-002 therefore needs durable receipt before acknowledgement, and retries need event identity beyond deterministic lead IDs. Missing addresses become `Unknown` in the current intake path, rather than a distinct incomplete classification. API version `v26.0` is observed in source; current Meta support has not been validated here.

**Immutable business audit is not yet established.** `audit_logs` has approved-user SELECT and service-role INSERT policies, but table ACL grants service_role UPDATE/DELETE/TRUNCATE too, and no audit_logs immutability trigger was found. A service-role client bypasses RLS. Harden grants and append-only enforcement for the PRD audit stream while preserving existing audit writers. Do not confuse immutable Facebook receipts with immutable underwriting/approval/contract history.

## Logical entity → existing table → additive plan

All proposed workspace-owned entities require membership/role RLS, server-side authorization, indexed workspace joins, and composite workspace foreign keys where practical. Proposed additions below are design decisions, not claims that columns already exist.

| PRD entity | Verified existing equivalent | Reuse/extension and conflict |
| --- | --- | --- |
| acquisition_campaigns | public.ad_campaigns; public.campaigns; public.fb_campaigns | Prefer ad_campaigns for acquisition attribution (leads already references it); retain campaigns outreach execution and fb_campaigns wizard state through explicit links. Add workspace, channel, budget_cents/limit and currency semantics; existing daily_budget/total_spend are numeric. Do not silently convert units or create a fourth disconnected campaign store. |
| campaign_events | fb_campaign_performance; webhook_jobs; raw_vendor_payloads | Performance aggregates and raw jobs are not immutable campaign events. Add append-only campaign event records referencing a durable provider receipt, campaign, workspace and access-controlled payload reference. |
| lead_sources | leads.source/inbound_channel/ad_campaign_id/ad_creative_id/form_submission_id; lead_form_submissions UTM fields | Add multi-touch association records linking existing lead, campaign and native/web receipt. Preserve current single-source fields for legacy UI compatibility. |
| contact_points | wholesale_ingest.contacts; leads.owner_phone_1/2/3, owner_email, phones | Extend/bridge existing contact records rather than duplicate skip-trace storage. Separate canonical normalized endpoint from provider observations and owner association; retain trace request/ordinal uniqueness. A contact can have phone and email today, so splitting into typed endpoints needs a stable source-ID crosswalk. Add owners/owner-property relationships because no owner entity exists. |
| contact_permissions | lead_form_submissions.raw_answers/request_manifest; facebook_lead_submissions.raw_answers; sms_resubscription_reviews | Add structured per-contact/channel/scope permission assertions referencing immutable source receipts. Include language version, provenance, timestamps, revocation and expiry. Unknown legacy evidence remains REVIEW; do not backfill assumed consent. |
| contact_suppressions | dnc_registry; email_suppressions; leads.dnc; ingest.contacts.dnc_status | Preserve legacy enforcement; extend with channel/scope/reason/source and normalized endpoint links or a compatibility projection. Check matching identities conservatively without revealing another workspace's records. Do not broaden one channel's opt-in into permission for another. |
| eligibility_decisions | Existing outreach/Retell SQL guards and receipt checks; no general decision ledger | Add versioned immutable decision records and private evaluation/execution functions. Preserve existing guards as additional constraints until independently validated. BLOCK/REVIEW prevent execution, including missing policy. |
| outreach_attempts | outreach_activity; sms_events; email_messages/email_delivery_events; call_events; retell_call_requests; buyer_outreach_log | Extend outreach_activity with workspace, actor, eligibility-decision link and provider reference; preserve provider-specific receipt ledgers and statuses. Never flatten accepted into delivered. |
| mail_jobs | No dedicated table in inventoried schemas | Add durable proposed/approved/submitted/fulfilled/failed/unknown jobs with lead/property/campaign, template/version, vendor, cost, idempotency and reconciliation. Enforce approval, frequency and budget at execution. Generic outreach_activity does not replace mail fulfillment state. |
| seller_intakes | lead_form_submissions; facebook_lead_submissions; qualification_results; leads | Extend qualification_results for channel-neutral intake classification/versioning or add a thin intake relation over immutable receipts. Preserve receipt IDs; link canonical property and lead without overwriting source answers. |
| underwriting_scenarios | deal_analyses; comps; repair_estimates; per-user development_workspaces | Extend deal_analyses with workspace/property, strategy, structured inputs/outputs, provenance/version/confidence and case relationships. Current exit_strategy CHECK does not represent all rental/development/flip cases; add a separate strategy field rather than silently relabeling legacy exits. Existing AFTER INSERT/UPDATE sync_deal_to_lead trigger must be tested so historical/case versions do not overwrite the current lead MAO. |
| acquisition_offers | offer_recommendations; leads.offer_price; deals.contract_price | Extend existing recommendation records or attach an offer lifecycle relation for amount, scenario/version, status, approvals and sent_at. Recommendations are not executed offers. Current authenticated approved-write policy is too broad for caller/agency roles. Preserve historic versions and prevent client approval bypass. |
| acquisition_contracts | deals | Extend existing deals with enforceable contract lifecycle, property/seller links, assignment provisions, title review, executed-document versions and closing approvals. Preserve existing stage/UI behavior during transition; stage text alone does not enforce the required state machine. |
| buyer_profiles | buyers; buyer_preferences; buyer_transactions | Extend workspace/verification provenance and preserve existing buy boxes, proof-of-funds fields, contact restrictions and history. Avoid another investor identity table. |
| disposition_records | deals; deal_matches; buyer_outreach_log | Extend deal-linked disposition state or add a lifecycle child for principal vs assignment, reviewed disclosures, selected buyer, deposits, expenses, approvals and net proceeds. Existing matches do not establish enforceability/title/marketing authorization. |
| integration_events | webhook_jobs; call_events; sms_events; email_delivery_events; facebook_lead_submissions | Extend webhook_jobs for durable provider/event identity and processing state, referencing existing provider receipts; separate immutable receipt content from mutable processing attempts if needed. Add provider + workspace/integration account + external event + event type uniqueness according to provider semantics. A leadgen receipt alone is not a universal webhook inbox. |

## Identity and tenancy decisions for the migration design

1. Introduce organizational workspaces and memberships linked to auth.users/profiles. Maintain existing approval/status as a prerequisite. Add workspace roles (owner/admin/operator/acquisition_caller/agency_manager) without repurposing the global profile role enum as cohort assignment.
2. Assign existing records to a reviewed Hilltop legacy workspace only after provenance/ownership verification. Do not grant every approved user membership automatically. Ambiguous ownership goes to an admin-only reconciliation queue. This backfill is a separately reviewed production operation, not authorized by the inventory.
3. Preserve canonical county property IDs and aliases. Bridge new intakes to properties and add explicit owner relationships with evidence. Resolve the current UNIQUE(lead_id) and one-native-receipt-per-lead constraints before reusing a single lead for repeat inquiries; keep append-only inquiry receipts and existing SMS foreign keys intact.
4. Scope new records and uniqueness by workspace where identity is tenant-local. Provider receipts additionally need account/subscription identity. Keep normalized suppression enforcement effective across matching identities without cross-workspace disclosure; exact controller-wide scope must follow approved policy.
5. Migrate protected readers/writers together. A nullable workspace column alone is not isolation, and a broad OR workspace_id IS NULL policy is unacceptable. Existing service-role APIs, RPCs, reporting views, county jobs and auth checks all need compatibility tests before enabling multiple workspaces.

## Remaining verification limits

Catalog presence is verified; existing user membership intent, record counts/data preservation, all function bodies, provider credentials, exposed-schema configuration, current Vercel flags/cron, storage buckets, legal policy and live end-to-end acceptance are not. Function inventory includes signatures/security/search paths, with full definitions only for the two authorization helpers. Further function/body dependency inspection is required before SQL. No backup/restore or RLS execution test is claimed.

## Contact crosswalk implementation follow-up

The production-based implementation adds `acquisition_contact_points` and `acquisition_contact_observations` as the typed source-ID crosswalk proposed above. Existing `wholesale_ingest.contacts` remains the provider observation store and `leads` remains the CRM source. Neither supports one normalized typed endpoint with multiple immutable source/lead links, which justifies these additions. No owner identity or permission is inferred. See PROGRESS.md for test evidence and remaining identity/retention work.

## Owner identity implementation follow-up

`acquisition_owners`, `acquisition_owner_properties`, and `acquisition_owner_contacts` implement explicit workspace-local identity and relationship assertions over canonical lead/property/contact IDs. This is an additive entity because inventory found no owner table. Source owner names come from `public.leads`, not `wholesale_ingest.properties` (which has no owner-name column). All assertions remain unverified; no fuzzy match or phone match creates shared ownership. Verification/correction/revocation workflows remain open.

## Permission evidence implementation follow-up

`acquisition_contact_permissions` structures and snapshots existing website/native consent receipts without replacing them. `acquisition_permission_revocations` is immutable and atomically creates a corresponding contact suppression; an invoker-security status view exposes revoked status under workspace RLS. Affirmative selection remains unreviewed and cannot authorize outreach. Source adapters currently support website SMS and native SMS/AI voice; policy-specific scope/expiry, additional sources/channels and effective-evidence selection remain open.

## Provider inbox implementation follow-up

`webhook_jobs` is extended with immutable acquisition integration/workspace/event identity, original body and hashes, and retention metadata. `private.acquisition_integrations` supplies privileged account-to-workspace routing with disabled defaults; no fourth campaign store is introduced. Acquisition receipts use a separate source/status namespace so existing pending-job processors do not claim them. Existing native Facebook/SMS receipt constraints remain unchanged pending explicit inquiry linkage. See PROVIDER-INBOX.md for retention, compensation and activation limits.

## Seller intake implementation follow-up

The thin `seller_intakes` relation links immutable canonical receipts to workspace-bound existing CRM leads. It avoids fabricating call_id/transcript values or activating HOT call triggers in qualification_results. `workspace_leads` now distinguishes human binding from same-workspace integration binding with an exclusive origin constraint. Canonical property/owner resolution remains separate; receipt-level retry deduplication does not claim cross-inquiry identity resolution. See SELLER-INTAKE.md.

## Intake underwriting provenance implementation follow-up

`acquisition_analysis_intakes` links existing `deal_analyses` to existing `seller_intakes`, qualification assessments and identity reviews. This small immutable relation stores source provenance rather than a parallel underwriting engine or CRM property. Composite tenant/source foreign keys and membership RLS protect the link. Existing analysis, offer and calculation functions gain current-source checks only for analyses with intake provenance. See INTAKE-QUALIFICATION.md for atomicity and compensation.

## Campaign catalog refresh — October 26

A fresh read-only production inspection confirms 70 columns across ad_campaigns/ad_creatives/lead_form_configs/lead_form_submissions and 14 inbound/outbound constraints. The detailed catalog, privileges, generated numeric columns and migration ledger are in `evidence/2026-10-26-campaign-catalog.json`. `CAMPAIGN-ISOLATION.md` records live shared/public access paths and the required ownership/child/service-write controls. The disposable acquisition harness now restores these parent tables and their previously omitted lead/form foreign keys before boundary migrations. Campaign ownership itself is not implemented by this fixture change.

### Source attribution implementation update (October 26)

The lead_sources logical entity is now represented by additive `acquisition_lead_sources` over original intake/lead/receipt/integration keys; no equivalent deployed relation existed in the read-only preflight. `acquisition_source_campaign_reviews` records versioned campaign association to exact `acquisition_campaign_links` reviews. Existing leads.source and ad_campaign_id remain unchanged. Canonical multi-touch rollups, campaign events, costs and funnel reporting remain incomplete; this is an association foundation, not completed FB-006 reporting.


### Canonical source reporting update (October 26)

`acquisition_property_source_touches` derives canonical property associations from existing source and current identity-review records; it creates no additional property, owner or lead table. A partial workspace/target/intake index supports bounded candidate retrieval. Current campaign snapshots are evaluated independently of historical captures. This read-only endpoint does not supply unique-owner, conversion or spend totals. See ATTRIBUTION.md for pagination, access and compensation details.


### Cost evidence catalog correction (October 26)

Live metadata inspection identifies `public.fb_campaign_performance` as the existing daily performance equivalent. Extend this relation rather than adding a parallel daily-cost table. Its `campaign_id` points to `fb_campaigns`, not the chosen acquisition campaign master `ad_campaigns`; `ad_set_id` points to `fb_ad_sets`. Both are nullable. The existing unique key `(campaign_id, ad_set_id, date)` is not revision identity and permits null-key duplicates. `spend` is numeric(10,2), defaults to zero, and `cpl` is generated from legacy spend/leads. These fields cannot be silently treated as complete, currency-verified acquisition costs.

The implementation must preserve legacy IDs/defaults/history while adding explicit workspace/acquisition-campaign identity, immutable evidence revision metadata, currency/account timezone, observed time, coverage and amount minor units. Acquisition rows must not populate default-zero legacy metrics or enter the existing command-center aggregates. Existing mutable legacy rows have no acquisition evidence provenance and must remain outside new coverage totals. Review both direct browser reads in ActiveCampaignsDashboard/PerformanceTracker and service-role paths when designing the boundary.

Metadata evidence: `evidence/2026-10-26-cost-catalog.json` contains 43 columns, 7 constraints, 6 policies, 6 indexes, 1 trigger and 63 role grants across fb_campaigns, fb_ad_sets and fb_campaign_performance. All three currently enable RLS. Approved-user policies are broad; service-role bypass and TRUNCATE/TRIGGER grants require explicit controls. Ledger remains 95 migrations/latest 20261023221455. Only catalog metadata was read; no production records or schema were changed.


### Cost evidence extension implementation

`20261026234504_acquisition_cost_evidence.sql` now adds the reviewed acquisition evidence namespace to existing fb_campaign_performance. No parallel cost or campaign master is created. Existing legacy metrics remain unchanged and are isolated from new evidence rows. New composite workspace FKs reference ad_campaigns and acquisition_campaign_links; read/write RPCs enforce current membership and reviewed account scope. See CAMPAIGN-COSTS.md for immutable revisions, null legacy metrics, read coverage and forward compensation.

## Inbound call catalog — October 26

Read-only production metadata is saved in `evidence/2026-10-26-inbound-call-catalog.json` (capture 2026-10-27 01:00:50 UTC / October 26 America/Chicago). It includes 5 existing tables, 61 columns, 20 constraints including inbound FKs, 18 indexes, 6 policies, 1 trigger and 122 grants. All 5 tables have RLS enabled. Migration ledger remains 95/latest `20261023221455`; feature `seller_intakes` does not yet exist in production. No production records or credentials were retrieved.

| Logical function | Existing equivalent | Compatibility and proposed extension |
| --- | --- | --- |
| Durable provider receipt | `webhook_jobs` | Reuse the existing acquisition receipt extension; add a distinct inbound integration/receipt contract. Persist only approved minimal data under the inbound privacy gate, never copy the full Retell call object into ordinary payload storage. |
| Inbound lifecycle ledger | `call_events` | Preferred extension: nullable lead/phone permits metadata-only receipt before identity review. Add explicit workspace/integration/call/event identity, projection version/hash and immutable audited controlled writes. Preserve required legacy disposition semantics with an explicit lifecycle category, not a fabricated seller outcome. Scope direct/legacy reads and close truncate/trigger escape paths. |
| Legacy AI call summary | `ai_call_records` | Requires phone_number and unique call_id globally; contains raw_payload, transcript, recording and qualification fields. Do not create fake phone values or reuse outbound qualification logic to force an inbound metadata receipt. Any later summary extension requires scoped privacy/identity rules and qualification/appointment FK fixture coverage. |
| Transcripts | `call_transcripts` | Contains raw/formatted text, globally unique call_id and generated word_count; do not populate for initial inbound deployment. Existing qualification_results FK chain must be covered before changing it. |
| Outbound call reservation | `retell_call_requests` | Requires lead, requesting user and phone; partial unique index prevents multiple unresolved requests per phone. It is not the inbound receipt or callback-request authority. Preserve it unchanged. |

Observed call_events policies permit authenticated access with an approved-operator restriction, not workspace membership. ai_call_records and call_transcripts similarly use approved-user SELECT/INSERT policies. webhook_jobs and retell_call_requests have RLS without exposed policies in this catalog; service-role privileges still require controlled server handling. Several tables grant TRUNCATE/TRIGGER to application roles, which row policies do not make safe for immutable inbound evidence.

The disposable fixture now restores call_events exactly (12 columns, PK/lead FK, 3 indexes, policies and grants) before acquisition boundary scans. It adds the JWT role claim/auth.role function needed by the observed policy. Tests prove legacy default/mutation behavior, preservation after lead binding, owner vs unrelated/caller reads, bound write denial, mandatory disposition/FK enforcement and the remaining unbound/grant gaps. This is not a claim that every inspected call table or the full production schema is restored.


Inbound ledger implementation update: local migration `20261027010558_acquisition_inbound_event_ledger.sql` now extends call_events with scoped metadata and a private approved-route configuration. The initially observed truncate/trigger gap is closed in the migration, and exact workspace/integration read isolation is tested. Existing webhook_jobs raw-body storage is not used for these privacy-minimized receipts; a raw archive remains gated. Six focused cases include populated legacy preservation. No production SQL has run; see INBOUND-VOICE.md for function contracts, limits and compensation.

## Inbound follow-up task inventory — October 26, 2026

A new metadata-only production query captured `evidence/2026-10-26-inbound-task-catalog.json` at 2026-10-27T01:33:52Z (October 26 locally). `tasks` is the existing equivalent for callback/escalation review; no separate callback table was found. Production still has 95 migrations, latest `20261023221455`, and no deployed seller_intakes (that relation is in the local acquisition migrations).

The task catalog contains 13 columns, 4 constraints, 2 indexes, 2 policies, no application triggers and 28 grants. ID defaults to uuid_generate_v4; title is mandatory; priority/status default to medium/pending. Nullable lead_id/deal_id/buyer_id reference existing CRM parents with ON DELETE SET NULL; assigned_to is nullable without an observed FK. There is no workspace, call identity, revision or explicit execution-approval column. These free-text legacy status/type fields cannot establish contact eligibility or callback authority.

Seven incoming task FKs belong to county-ingestion operations: monitor_incidents, expected_runs, daily_digests, scoring_incidents, propstream_handoffs, bulk_supervision and property_alert_days. Preserve task IDs and legacy rows; full populated upgrade acceptance must include those dependents. The focused fixture restores the task table's actual outgoing FKs, columns/defaults, indexes, policies and app/service grants before acquisition boundary scans, but does not pretend to recreate the seven county tables.

The observed permissive authenticated policy plus approved-operator restriction is not tenant isolation for a call-only task. Existing acquisition related-record policies scope tasks with bound lead/deal parents, but a task without those parents remains broadly readable by approved legacy users. Broad TRUNCATE/TRIGGER grants remain another gap. Future task extensions must add an explicit scoped namespace, controlled audited service writes, immutable request evidence and bounded membership-checked reads. Direct legacy reads must exclude acquisition task records even before a lead exists; database defaults must not turn them into executable callbacks.

Planned reuse: keep seller-intake snapshots in seller_intakes, extend its Facebook-only receipt/source constraint with a composite inbound-call origin, and keep callback/human-escalation review work in tasks. Call-scoped request/revision identity must be enforced independently of phone/address matching. A private request ledger may coordinate idempotency and audit but must not become a parallel seller CRM. These are design decisions based on observed schema, not implemented migrations in this checkpoint.
