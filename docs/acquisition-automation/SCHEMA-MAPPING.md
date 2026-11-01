# Acquisition automation — verified schema mapping

Observed October 25, 2026, America/Chicago (catalog checkpoint 2026-10-26 02:31:52 UTC). Status: historical inventory with additive implementation tracked in PROGRESS.md; no production migrations applied.

## November 1 — post-execution title findings storage

`acquisition_contract_reviews` remains the logical title/contract review entity, with new bounded `title_findings` and `title_sources` JSON, exact execution-transition identity and original-withdrawal reference. `private.acquisition_contract_review_policies` adds the distinct `title_findings` / `title_report` pairing without provisioning authority. `acquisition_contract_transitions` gains a scoped execution identity for the foreign key; historical transitions and contract versions remain unchanged. New source/shape validators are private, invoker functions with fixed search path and no application-role grants. Existing RLS and immutable review controls are retained. Inventory: `evidence/2026-11-01-title-findings-local-catalog.json`. Migration: `20261101055752_acquisition_title_findings_storage.sql`. No production application authorized; forward compensation preserves historical rows and keeps the new path disabled.

## November 1 — controlled title review policy and writer

The existing private contract-review policy entity adds nullable title report age rules (seconds for exact instants; days plus named timezone for calendar dates). No policy rows/default authority are added. The existing public immutable review entity adds `title_policy_snapshot`, restricted to non-withdrawn title findings; current approval requires an exact match to the current policy. Functions write/read the existing ledger with the original workspace, version, execution, evidence and audit constraints. No new table or public direct-write grant. Candidate97 inventory in `evidence/2026-11-01-title-source-local-catalog.json` describes the unchanged source tables before this additive extension; candidate97 itself added only a private resolver function.

## Evidence and baseline

Fresh lifecycle-focused read-only inspection on October31 at2026-11-01T01:56:26Z is saved in `evidence/2026-10-31-lifecycle-catalog.json`. It covers100 columns,9 constraints,72 grants and current indexes/policies/triggers for deals, buyers and buyer_preferences. Hosted latest migration remains20261023221455. A preceding metadata query also confirmed RLS enabled on these three tables and no hosted acquisition_contract tables. This refresh does not replace the broader baseline inventory or prove hosted feature acceptance. No seller/buyer records were read.

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

Task implementation update: local migration `20261027013724_acquisition_inbound_review_tasks.sql` now adds scoped callback/escalation review evidence to tasks, unique integration/request identity and call/kind revisions, controlled immutable writes, membership-checked reads and namespace isolation. Truncate/trigger grants are removed for application/service roles. Existing task IDs and nullable legacy columns are retained; no parallel task table or owner/lead merge is introduced. Seller-intake source/receipt extension remains pending. See INBOUND-VOICE.md for transaction semantics and compensation.

Inbound intake implementation update: local `20261027015624_acquisition_inbound_intakes.sql` reuses seller_intakes and acquisition_lead_sources with additive scoped call-event origin and immutable revision identity. Facebook receipt constraints become source-specific without changing existing rows. The shared source trigger handles inbound evidence without ad metadata; the qualification evaluator invalidates superseded inbound snapshots. Each call creates one new existing CRM lead, later snapshots reuse that lead, and no phone-only merge occurs. Inbound source revision grouping/UI remains pending before activation; see INBOUND-VOICE.md for limits and compensation.

## Inbound request queue — October 26, 2026 inspection

Read-only production catalog recheck confirmed 95 applied migrations, latest `20261023221455`, and unchanged legacy `public.tasks`: 13 columns, four constraints, two indexes and the authenticated/approved-operator policies recorded in the task catalog. The acquisition task columns and protective policies exist only in the pending local migrations. No production task data was queried.

CLI-created `20261027023450_acquisition_inbound_request_queue.sql` adds only a partial `(workspace_id,id)` index and a private SECURITY DEFINER / public SECURITY INVOKER read RPC. It reuses `tasks`; no parallel task or lead table. Authorization is the existing session-aware `acquisition_role`, limited to owner/admin/operator. Private search path is empty; PUBLIC, anon and service_role have no execute grant. Existing task RLS, immutable triggers and county-task relationships are unchanged.

The queue selects the highest revision per workspace/integration/call/request kind and returns at most 50 rows plus an internal lookahead for the next cursor. It includes calls without seller intakes. Superseded evidence remains in tasks and call history. Responses explicitly identify per-read revision scope, unavailable review completion state, and no execution authority. UUID traversal is not chronological; new requests or revisions can require a refresh from the first page.

Compensation: turn off the acquisition surface and revoke authenticated EXECUTE on both queue RPCs in a separately reviewed forward migration. Preserve task evidence and prior migrations. The new index may remain without behavior effects; no historical replay or production migration is authorized. Reviewed current function security guidance: https://supabase.com/docs/guides/database/functions .

## Inbound request review ledger

The next read-only deployed check again found 95 migrations (latest `20261023221455`); matching public tables were tasks, audit_logs and unrelated sms_resubscription_reviews. Production audit_logs has the expected nine legacy columns. The local workspace/audit extensions and task constraints were inspected before writing SQL. No existing inbound task review ledger was found.

CLI-created local `20261027024045_acquisition_inbound_request_reviews.sql` adds `(workspace_id,id)` uniqueness to tasks and an append-only `acquisition_inbound_request_reviews` relation. This stores decisions against existing task IDs; it is not a parallel callback queue or CRM. A composite FK prevents a review from referencing a task in another workspace. SELECT uses actual owner/admin/operator membership; all app/service DML, TRUNCATE and TRIGGER grants are revoked. Updates/deletes are also rejected by the existing immutable-evidence trigger. Only private SECURITY DEFINER/public INVOKER RPCs can record decisions.

Mutation locks activation, workspace, reviewer session/profile/membership and target assignee eligibility through commit. It shares the call lock with inbound request submission, uses request fingerprints and optimistic review sequence, and records minimal immutable audit metadata. Exact retries return the historical receipt; changed ID reuse conflicts. Current state separately evaluates request supersession, activation and actor/assignee membership timestamps and approval.

Compensation: disable the acquisition surface and revoke authenticated EXECUTE on the two review RPC pairs through a separately reviewed forward migration; preserve decision/task/audit evidence. No destructive rollback or production migration is authorized. The pre-existing queue remains a discovery-only surface until its status projection and UI are wired in a subsequent migration.

## Reviewed queue projection and filters

Read-only migration ledger recheck remains 95 applied / latest `20261023221455`. Local task/review dependencies, membership checks, indexes and v1 queue were inspected before CLI creation of `20261027025554_acquisition_inbound_queue_review_status.sql`. It adds a private/public v2 read RPC pair, with no table, grant widening or data rewrite. Existing v1 remains callable for unchanged clients.

The v2 query reuses `acquisition_inbound_request_state` rather than duplicating stale-review logic. It exposes only current derived status, review sequence/currentness and assignee alongside the existing minimal request summary. Server filters support open/all/specific status and all/mine/no-current-assignee. `mine` derives auth.uid(); clients cannot choose another actor. Filtering occurs before page limit and next-cursor lookahead. A lateral barrier avoids repeated evaluation of state fields for the same candidate. Sparse filters may inspect more candidates than the returned page; no large-volume latency claim is made.

Compensation: route the application back to its prior compatible release and revoke authenticated execute on the v2 function pair in a reviewed forward migration. Keep v1 and all evidence. Current API/UI require v2 and must not silently fall back to stale or unfiltered status. No production migration is authorized.


### Inbound property lookup extension

Rechecked production metadata before SQL: 95 applied migrations, latest `20261023221455`; county properties retain canonical address_std/city/state/unit and lead_id, with primary-key, unique lead and partial parcel indexes and the wholesale_worker policy. Local acquisition enrollment/boundary migrations supply tenant restriction. No new entity or property copy is introduced. `20261027031552_acquisition_inbound_property_lookup.sql` adds only service-role RPC functions over existing route/call/intake/workspace enrollment/property records; signed server context selects scope. The exposed function is invoker, implementation definer with empty search_path, and both deny anon/authenticated/PUBLIC execution. See INBOUND-VOICE.md for return projection and compensation. Production remains unapplied.


### Inbound restriction provenance

Production metadata rechecked before SQL: 95 applied migrations/latest 20261023221455; acquisition ledger tables remain unapplied. Existing public.dnc_registry and leads.dnc metadata were inspected without seller data or mutations. Locally inspected acquisition suppression constraints/indexes/RLS/triggers/grants, contact normalization, eligibility, route/call constraints and task review functions before extending them. `20261027140038_acquisition_inbound_contact_restrictions.sql` adds six call-provenance columns and a partial call index to acquisition_contact_suppressions. Its origin CHECK preserves legacy operator requirements and permits null actor/lead/contact/channel only for a fully sourced inbound record with immutable channel-array evidence. No contact identity or actor is fabricated; no duplicate table is introduced. Existing immutable audit logging records the action and scope. The existing human suppression RPC now uses NULL-safe identity comparison to prevent collision with inbound-origin request IDs. New provider RPC is public invoker/private definer with empty search_path and service-only execution; endpoint matcher is private with no application execute grants. See INBOUND-VOICE.md for compensation and current channel limits.

### Mail template extension — October 28, 2026

Rechecked deployed history (95 migrations, latest 20261023221455), mail/template tables and ad_campaigns/ad_creatives columns, constraints, indexes, policies and triggers before SQL. No dedicated mail template/jobs table exists. Reuse ad_campaigns for direct_mail campaigns and extend ad_creatives for immutable printed draft versions through local migration 20261028020606. New workspace/campaign composite FK and scoped version uniqueness preserve tenant identity; restrictive RLS separates legacy and acquisition rows. Existing creative updated_at trigger remains; immutable mail rows cannot be updated through it. New guarded creator replaces only the creative campaign-association trigger; form/lead campaign guards remain in place. The additional lead-creative guard locks a visible parent before attribution, preventing a concurrent FK wait from adopting a mail draft. mail_jobs still requires a separate additive design; draft content is not fulfillment state. See DIRECT-MAIL.md for compensation and release limits.

## Mail destination review ledger — October 28, 2026

Read-only preflight still found 95 deployed migrations (latest 20261023221455), no mail-destination/tracking review master, and unchanged ad_campaigns/ad_creatives column, constraint, index and RLS definitions. Existing campaign, creative and SMS review relations are not equivalent to controlled destination review history. Local destination/template/campaign and membership/session dependencies were inspected before CLI creation of `20261028181631_acquisition_mail_destination_reviews.sql`.

The additive `acquisition_mail_destination_reviews` ledger references existing ad_campaigns by composite workspace/campaign key. It stores immutable destination revisions and approve/withdraw events, not a new campaign or provider-routing master. Destination identity is unique by workspace/version and cannot migrate between campaigns. RLS reads allow actual owner/admin/operator membership; authenticated owner/admin MFA/session checks govern controlled writes. No production migration was run. Content review and mail-job ledgers remain pending.

### Content preparation inspection — October 28, 2026

Reinspected deployed metadata before local preparation SQL: 95 migrations, latest `20261023221455`; existing ad_campaigns/ad_creatives columns, indexes, primary/foreign constraints and permissive plus approved-operator RLS policies remain unchanged. No equivalent mail preparation function or dedicated content master exists. The local migration `20261029012211_acquisition_mail_content_preparation.sql` reads the prior unapplied workspace/creative/destination extensions rather than duplicating those entities. It adds private SECURITY DEFINER (empty search_path) plus public SECURITY INVOKER functions with authenticated-only execution and actual membership/session checks. No table, index or policy changes; no production DDL. Its predecessor migrations must be present first. Compensation and acceptance boundaries are in DIRECT-MAIL.md.

### Content review ledger inspection — October 28, 2026

Reinspected deployed metadata before `20261029013306_acquisition_mail_content_reviews.sql`: still 95 migrations/latest 20261023221455; no dedicated mail content review equivalent. Related creative/campaign columns, indexes, primary/foreign constraints and RLS inspected. The local migration adds only the content decision ledger and ad_creatives(workspace_id,id) unique key for tenant-safe references, using prior unapplied workspace/template/destination migrations. Existing creative bodies and destination evidence remain their respective masters. New table has actual-membership RLS and no raw mutation grants; private definer functions have empty search_path and public wrappers are invoker-only. Compensating procedure and remaining release gaps are in DIRECT-MAIL.md. No production migration executed.

### Proof context inspection — October 28, 2026

Before `20261029014552_acquisition_mail_proof_context.sql`, reinspected deployed migration history (95/latest 20261023221455), wholesale_ingest.properties columns, primary/unique/foreign/check constraints, indexes and worker-only RLS. Workspace enrollment and content ledger are prior unapplied local migrations. New private definer/public invoker read functions join enrolled canonical property identity with current content review, return a fixed non-owner projection and grant only authenticated execution after actual membership/session authorization. No table/index/policy change, data copy, production DDL or provider action. DIRECT-MAIL.md documents compensation and live acceptance gaps.


## Evidence registry inventory and mapping — 2026-10-29 UTC

Metadata-only inspection saved in `evidence/2026-10-29-evidence-catalog.json`: deployed history remains 95 migrations/latest 20261023221455. Inspected relevant columns, constraints, indexes, RLS and policies. No public document/evidence/artifact table was found. Existing storage.objects/storage.buckets are managed storage metadata and are not a review/provenance registry; they are not recreated or mutated here. Prior inspection found no buckets or storage policies.

| Logical entity | Mapping | Isolation and compatibility |
| --- | --- | --- |
| Retention policy configuration | New private.acquisition_evidence_policies | Deployment-controlled reviewed configuration; workspace/purpose/version, approval reference, explicit retention seconds and validity/revocation. RLS with no application grants. No default rows or invented business duration. |
| Evidence identity and expectations | New public.acquisition_evidence_artifacts | Immutable metadata; composite workspace/campaign and workspace/policy foreign keys. Expected hash/size/type are unverified. Existing actual-membership/session helpers restrict exposed reads; only guarded RPC writes. |
| Evidence revocation | New public.acquisition_evidence_revocations | Append-only, one terminal revocation per artifact; composite workspace/campaign/artifact association. Owner/admin MFA and current-session checks; preserves registration and audit history. |
| Evidence audit | Existing public.audit_logs | Minimal registration/revocation events, reusing the acquisition workspace and immutability extension. |
| File storage | Existing storage schema, future private bucket/policies | No bucket or object policy is added by this migration. Upload, quarantine, immutable object rules and verification linkage remain required. |

Local CLI-generated migration: `20261029022851_acquisition_evidence_registry.sql`. Existing public campaign/workspace/auth/audit masters are reused. Public entry points are invokers over private definers with empty search_path and restricted EXECUTE. Raw insert/update/delete/truncate is denied to application roles. New tables do not backfill, rewrite or approve existing mail review evidence. Registration is deliberately unavailable until reviewed retention configuration exists.

Compensation: revoke registration EXECUTE on both public/private entry points to stop new registrations while preserving metadata, state reads and revocation. Do not drop ledgers or erase audit events. Retire an approved policy through a reviewed configuration change setting revoked_at; historical rows remain. Application-facing policy administration/auditing remains future work, and no policy configuration changes are authorized by this migration alone.

### Storage access inspection — 2026-10-29 UTC

Rechecked managed storage grants, RLS, buckets, policies and deployed migration history in read-only transactions. Saved `evidence/2026-10-29-storage-access-catalog.json`: zero buckets/policies, RLS on both tables, authenticated/anon SELECT/INSERT/UPDATE/DELETE grants, privileged service-role grants; ledger still 95/latest 20261023221455. Column/constraint/index inventory remains in the preceding evidence catalog. Inspected operation helper definitions and current official operation names.

Local migration `20261029024603_acquisition_evidence_storage.sql` adds one private bucket configuration and scoped permissive/restrictive object policies over the existing managed schema. Exact artifact key joins reuse registry/workspace/profile/session/policy masters. It creates no replacement object table, changes no global grants and performs no actual object writes. Existing bucket-name collision aborts the transaction. Service-role bypass, request-time race limitations, isolated fixture scope, forward compensation and remaining real-Storage acceptance are documented in EVIDENCE-STORAGE.md. No production DDL or bucket change occurred.


### Evidence discovery extension

Local migration `20261029035546_acquisition_evidence_discovery.sql` maps the guided evidence picker to the existing `acquisition_evidence_artifacts`, `acquisition_evidence_revocations`, private `acquisition_evidence_policies` and `ad_campaigns`. It adds no duplicate entities or data columns. The bounded private read function/public invoker wrapper reuse actual membership/session authority and current artifact state. See EVIDENCE-STORAGE.md for projections, policy selection, pagination and forward compensation. Live metadata recheck still shows ledger 95/latest 20261023221455 and no deployed evidence registry/policy tables.


### Evidence upload capacity

`20261029142852_acquisition_evidence_upload_admission.sql` adds private `acquisition_evidence_upload_slots`, an operational two-slot-per-workspace table referencing existing workspaces/profiles and composite registry identities. No equivalent local capacity table was found; existing evidence, contact and campaign entities are reused. Application roles receive only guarded function execution, no slot-table privileges. See EVIDENCE-STORAGE.md for limits, expiry/reuse, protection scope and forward compensation.


## Signed scan observation ledger — October 29, 2026

Rechecked production: 95 migration entries, latest 20261023221455; evidence registry/key/verification tables absent; zero Storage buckets; pgcrypto in extensions. Local migration 20261029184129 reuses the artifact/policy/revocation/campaign/workspace/session/audit dependencies and adds private workspace-scoped signing-key configuration plus an immutable public observation ledger. See EVIDENCE-ATTESTATIONS.md for composite relationships, RLS/grants, empty-by-default provisioning, signature contract, preservation tests and forward compensation. This is persistence of a signed observation, not approval or preview clearance. No production DDL ran.


### Portal receipt origin extension (proposed migration 20261031202407)

Reuse public.lead_form_submissions for exact portal wording/submission evidence, workspace/campaign and request fingerprint; preserve legacy nullable scope. Composite form/lead foreign keys bind acquisition records. workspace_leads gains a distinct portal receipt origin; seller_intakes and acquisition_lead_sources gain portal receipt references, with the latter retaining the exact originating campaign. Existing Facebook and Retell branches remain explicit. No parallel lead/owner/property store or fabricated integration is introduced. Scope reads use existing workspace role checks; direct service/browser writes cannot create scoped receipts; immutable receipt history and the existing legacy recovery guards protect them. See ONLINE-OFFER-PORTAL.md for compensation and remaining HTTP/abuse/seller-interface work.


### Portal operational admission (proposed migration 20261031203609)

No existing production equivalent was found in the inspected catalog. Private policy, short-lived admissions and aggregate denial totals support cross-process abuse limits; they do not replace receipts, leads, owners or contact eligibility. Admission identity binds the existing immutable form/workspace/campaign plus purpose/request digest. Policy revisions use the existing audit master with an additional immutability guard and tenant-browser read exclusion for global policy events. Operational digests have five-minute retention with explicit disabled-policy cleanup; live monitored cleanup remains a release requirement.

## Local verified portal acceptance (migration 20261031204520)

Extends private admission records with consumption identity and the policy with exact bot hostname. Adds private short-lived verification bindings; no duplicate CRM entity. Old receipt RPC access is revoked for application roles; service completion requires fresh matching admission, server verification and publication, with atomic receipt creation and audit. Browser/raw service ledger access is denied. Operational cleanup includes expired verification rows; no cleanup schedule or production migration is activated.

## October 31 contract/disposition refresh

Read-only catalog at 2026-10-31 22:12:59 UTC confirmed the production ledger remains `20261023221455`. Evidence: `evidence/2026-10-31-contract-catalog.json` and `evidence/2026-10-31-contract-legacy-functions.json`. Inspected live columns, RLS, constraints (including inbound references), indexes, grants, triggers and pipeline create/update/validation/task function definitions. No seller rows or secret values read; no production writes. Current Supabase RLS documentation was reviewed: https://supabase.com/docs/guides/database/postgres/row-level-security.

- `deals` is the canonical contract/disposition parent. It already carries lead, contract/buyer prices, gross assignment fee, earnest money, contract/inspection/closing dates, buyer, title details and document URLs. Extend it; use child version/evidence/event relations only for immutable history. Existing tasks, notifications, agent logs, matches and outreach reference this ID and must retain it.
- Existing `deals_one_active_lead` excludes only closed/cancelled. An acquisition `expired` state cannot be copied blindly into legacy stage or it would retain the active-lead reservation. Disputed must retain its reservation. The implementation needs an explicit reviewed projection, not an altered historical index or automatic terminal backfill.
- `deal_handoff_valid` currently requires a buyer and assignment URL for closed deals. It cannot validate principal acquisition unchanged. Add a scoped contract path and preserve legacy validation for untouched deals; do not fabricate an assignee/assignment document to close a principal purchase.
- The live deadline columns are dates, not timestamps. Preserve their precision. An acquisition timestamp requires reviewed document time/time-zone evidence; never infer midnight or reuse the task scheduler's 17:00 America/Chicago reminder as the contractual deadline.
- `buyers` (53 observed columns), `buyer_preferences` (one row per buyer), `buyer_transactions`, `deal_matches` and `buyer_outreach_log` are reusable. Their present approved-user policies are not tenant policies. Buyer workspace scoping must include dependent reads/writes, cascade paths and existing service-client routes before acquisition selection. Do not create a disconnected buyer_profiles clone or automatically assign historical buyers to a workspace.
- Live buyers/preferences still grant TRUNCATE/TRIGGER to application roles; RLS cannot secure those operations. The new scoped history must explicitly revoke table-wide bypass privileges as appropriate, while validating retained legacy behavior. Deals has service-role write and table-wide privileges; private controlled writes and scoped raw-write protection must close that path for acquisition rows.
- Existing Python CRM requests switch to user JWT/RLS in acquisition mode. The legacy pipeline RPCs are service-only, use supplied operator IDs and populate a deals composite row. They are not the new authorization boundary. Composite-row expansion, legacy payload fields, exact retry manifests and task side effects must be covered in compatibility tests when adding columns.

This inventory changes the implementation design but does not claim persisted contracts, isolated buyers or approved disposition already exist. No migration has been created for this increment.

Implementation follow-up: CLI-created migration `20261031221633_acquisition_contract_drafts.sql` now extends deals and adds immutable draft-version receipts using the inspected mapping. Six focused tests passed; the full enlarged-catalog rehearsal is pending in process 8324. No production schema changed.


## Contract document registry candidate — October 31

CLI-created migration `20261031224723_acquisition_contract_document_registry.sql` extends the existing evidence artifacts/revocations and reviewed retention policy tables. It does not create a parallel artifact store. Each artifact has exactly one target: unchanged mail campaign/purpose, or canonical contract ID/version with a composite workspace FK to `acquisition_contract_versions`. Revocations bind the exact same target. Existing populated mail records remain byte-for-byte equal on their original columns; the new target columns are null.

Contract registration, revocation and state RPCs derive current actor/session/MFA/workspace role, serialize against canonical deal creation, preserve exact request hashes and immutable audits, and reject legacy mail-route access to contract artifacts. Existing RLS and raw-write restrictions remain. No contract Storage upload is allowed: the unchanged upload guard still requires an actual draft mail campaign. Existing read guards enforce private bucket, exact immutable path, current policy/retention/revocation, membership/session and operator ownership. Document classification is not a signature/title/legal approval.

Fresh live check still shows ledger 20261023221455 and no candidate evidence/contract tables; evidence/2026-10-31-contract-registry-live-check.json. Local candidate manifest now has 58 migrations. Actual rehearsal passed 26 access probes, 95 application workflows and 58 gateway checks; original 24 historical records and 103 definitions preserved. Compensation remains disable activation and retain artifacts/versions/audit history, not a destructive down migration. Upload admission, signed scan bindings, immutable reviewed terms and lifecycle transitions remain required.

## 2026-10-31 shared contract upload admission candidate

Fresh read-only live check: ledger `20261023221455`; `private.acquisition_evidence_upload_slots` and `public.acquisition_contract_versions` absent. Local migration 59 extends existing candidate upload slots with nullable contract ID/version, exclusive target shape and composite artifact identity. Existing private RLS/no direct application grants remain. Mail function signature and aggregate limits are preserved; no new table or Storage grant. Compensation is activation off plus normal reservation expiry, preserving all evidence/history. Validation status is in CURRENT-STATUS.md.

## 2026-10-31 contract Storage authorization candidate

Fresh metadata query reports ledger `20261023221455`, no candidate acquisition_evidence_artifacts and no returned Storage object policies. Migration 60 modifies only private.acquisition_evidence_object_access(text,boolean); its existing function privileges and restrictive Storage policies remain. Contract upload checks canonical draft/version and the exact active shared reservation; existing mail dispatch and retained read semantics remain. No live DDL was issued. See CONTRACT-DOCUMENT-PERSISTENCE.md for compensation and verification boundaries.

## 2026-10-31 contract document discovery candidate

Live read-only verification still reports ledger 20261023221455 and no acquisition_evidence_artifacts or acquisition_contract_versions. CLI-created migration 61 adds private-definer/public-invoker contract_document_candidates RPCs only, with authenticated-only execution. It reuses canonical versions, shared retained artifacts and private reviewed retention policies; no new entity, table privilege, runtime setting or evidence record. Compensation: keep activation disabled and preserve all history; omit the read-only feature if necessary.


## Contract scan observation extension (candidate migration 62)

CLI-created `20261031234409_acquisition_contract_observations.sql` extends the existing public acquisition_evidence_verifications ledger with mutually exclusive campaign or contract/version/purpose targets. Composite artifact-purpose and private key-scope foreign keys enforce exact workspace/target identity. Existing mail columns, immutable trigger, workspace/actor RLS, SELECT-only grants, audit behavior and detected-byte index remain intact. An added contract-history index supports version-scoped lookup. No duplicate verification table is created.

New private acquisition_contract_verification_key_scopes records separately reviewed purpose authority for existing workspace signing keys, with reviewer, approval reference, bounded validity and revocation. It has RLS, no application-role grants, and no automatically seeded rows. Existing keys gain no contract authority. Public record_contract_document_verification is security-invoker; its private definer uses an empty search path, exact HMAC domain/context, current MFA actor/session/membership, version/registry/purpose/retention checks and shared artifact/hash locks. Historical exact retry returns only persistence evidence and all preview/legal/execution flags remain false. A detection is visible to existing shared hash-alias holds across both document targets.

Fresh hosted metadata before writing SQL remains ledger 20261023221455 with candidate artifact/verification/version tables absent (evidence/2026-10-31-contract-attestation-catalog.json). Candidate predecessor constraints, indexes, RLS, grants and latest verification function overrides were read locally. Seven focused disposable database cases passed. Full historical-catalog rehearsal passed 62 migrations, 26 access probes, 119 application workflows and 69 actual local gateway checks; historical records/definitions and Storage fixture remained intact. See evidence/2026-10-31-contract-observation-gateway-result.json. Compensation preserves all observations/artifacts/audits, revokes contract key scopes, and keeps downstream acquisition activation disabled. No production migration approved or applied.


## Contract current scan assessment (candidate migration 63)

CLI-created `20261031235803_acquisition_contract_scan_state.sql` adds private-definer/public-invoker read-only `contract_document_scan_state` functions. It reuses shared artifacts, immutable verifications, exact version/purpose identity, private reviewed key scopes, retention policies, memberships/profiles/sessions and the existing detected-byte index. No table, raw grant, duplicate ledger or new key scope is created. Both functions have an empty search path, explicit authenticated-only execution and current MFA/workspace/role checks; operators can assess their own artifacts only. Existing table RLS, constraints, indexes and history remain unchanged.

The current receipt identifies an observation only while its signer, contract-purpose scope, original membership/profile/session and retention policy remain current. Any detected same-workspace matching bytes keep a quarantine flag across mail/contract aliases. Retained revoked/expired status remains visible without private file URLs, signer details, other artifact identities, preview or approval authority. Compensation: omit this read feature and keep activation disabled; preserve all history.

Fresh hosted metadata remains ledger 20261023221455 with candidate artifact/observation/key-scope tables absent (evidence/2026-10-31-contract-scan-state-catalog.json). Reviewed local predecessor definitions include registry, ledger, key scopes, hash/history indexes, RLS and grants. No hosted DDL. Five focused SQL cases passed after correcting a synthetic scanner-version fixture; full-catalog testing includes an additional original-actor revocation case. Current validation status is recorded in CURRENT-STATUS.md. Function privilege guidance checked against https://supabase.com/docs/guides/database/functions.

## Contract human review ledger (candidate migration 64)

`20261101000910_acquisition_contract_reviews.sql` adds private reviewer policies and a public immutable review ledger; existing canonical deals/versions and shared artifact/verification records remain the source of identity. No equivalent human contract-review ledger was found in the preceding catalog. Composite foreign keys bind workspace, contract version, artifact purpose, exact verification and approved reviewer policy. Both tables use RLS; only owner/admin MFA users can read the public ledger, with no application raw writes or private policy access. Private definer functions have empty search paths and public invoker wrappers. Policy rows are not seeded. Immutable decisions and atomic audits preserve retries and withdrawals.

Hosted metadata inspection before this candidate reported ledger 20261023221455 and no candidate contract-review/version tables; no hosted DDL was applied. Full disposable upgrade and actual gateway evidence is in evidence/2026-10-31-contract-human-review-gateway-result.json. Compensation revokes policy authority/pauses activation while preserving immutable decisions and historical records.

## October 31 — exact-document review choices (candidate migration 65)

Fresh read-only hosted metadata remains ledger 20261023221455 with candidate versions/reviews/policies absent; evidence/2026-10-31-contract-review-candidate-catalog.json. Inspected predecessor functions, tables, grants, indexes and constraints. CLI-created 20261101002427_acquisition_contract_review_candidate.sql adds only private-definer/public-invoker read functions with empty search paths and explicit authenticated grants; no new tables or policy activation. Current Supabase function/privilege documentation checked.

The exact workspace/contract/version/kind/artifact read uses current owner/admin MFA authority and returns a deterministic most-recent active policy explicitly assigned to that reviewer. Evidence must be the current exact verification and pass the shared retained-evidence checks. Maximum expiry is the earliest of retention, key/purpose, policy, scanner/reviewer sessions and configured review duration. Discovery grants no execution authority and writes no reviews/audits. It provides the latest sequence and original-reviewer withdrawal identifiers even while acquisition is paused or evidence/policy authority is revoked. A different document or purpose is rejected. No private signing material, approval notes or unrelated identities are returned. Compensation omits/revokes this read interface while retaining all review history.

Four focused database cases passed in 18.453s, covering exact scope/MFA/role restrictions, no mutations, limiting session expiry, policy/evidence revocation and withdrawal during pause. Full disposable catalog/gateway rehearsal session 16348 is live (/tmp/contract-review-candidate-upgrade.log); do not restart or declare it passed before terminal evidence. Manifest includes migration 65. Typed candidate API, app decision controls and recovery are still required. No production changes.

## Contract terms/version mapping — candidate 66

Canonical contract: public.deals; immutable versions: public.acquisition_contract_versions, extended with terms, previous_version and actor session. No new contract entity. New acquisition_contract_term_sources links each versioned term to its original artifact/version and verification through workspace-scoped composite foreign keys. Existing document and review keys are preserved; new versions invalidate prior current-review status. Candidate migration 20261101004230_acquisition_contract_terms.sql changes the single-version constraint and protected-deal trigger only to permit controlled increment-by-one draft versions. It adds an authenticated private-definer/public-invoker save RPC, empty search paths, explicit grants and role-scoped RLS. Original draft fields and legacy-stage restrictions remain. Full populated-upgrade verification passed on the final66-migration candidate, preserving24 historical records,103 table definitions and the Storage fixture. See evidence/2026-10-31-contract-terms-gateway-result.json. Production remains untouched.

## Candidate67 — original contract document references

Existing acquisition_contract_term_sources already associates known terms with exact original-version evidence; no duplicate link or upload is created for those sources. New acquisition_contract_document_links stores separately selected earlier same-contract sources, including target/source versions, artifact/hash/verification, creator session and note. acquisition_contract_document_link_revocations is append-only and independently withdraws a reference without revoking the original artifact. Workspace-scoped composite FKs bind target version and original artifact/verification. Both tables enable RLS with actual owner/admin/operator membership and MFA; no raw writes or service-role grants. Definers remain private, wrappers invoker, search paths empty, execute grants explicit.

Fresh read-only hosted catalog evidence:2026-10-31-contract-document-links-catalog.json. Existing candidate review composite keys, original scans and Storage paths remain unchanged. Internal reference resolution recognizes native artifacts, persisted term sources and explicit links; public reference state rechecks exact retained source authority. Full67-migration populated upgrade passed with149 workflows and86 local gateway checks; evidence/2026-10-31-contract-document-links-gateway-result.json. Compensation retains history and disables new functions/activation. Current guidance checked: https://supabase.com/docs/guides/database/postgres/row-level-security .

## Candidate68 — separate review target and original evidence version

Existing public.acquisition_contract_reviews remains the canonical ledger. Add evidence_version plus generated source_version=coalesce(evidence_version,contract_version); historical rows are not updated and retain their original source binding. Original target FK is unchanged. The two evidence FKs are replaced transactionally with source-version composite FKs to the same artifact/verification keys. No RLS, role grant, public request/receipt shape or request hash is broadened. Functions require a retained same-contract target reference and current original evidence; withdrawn links invalidate current approval. Withdrawal copies prior source_version and can reduce authority after revocation. Compensation pauses acquisition/revokes reviewer policy authority; never restore old evidence FKs over cross-version decisions.

Fresh hosted catalog evidence:2026-10-31-contract-review-source-catalog.json. Focused populated-history/retry checks and the full68-migration upgrade passed, including154 workflows and89 actual local gateway checks; evidence/2026-10-31-contract-source-review-gateway-result.json. PostgreSQL17 generated-column reference: https://www.postgresql.org/docs/17/ddl-generated-columns.html .

## Candidate 69: contract reference discovery

`20261101011718_acquisition_contract_reference_discovery.sql` adds no tables. It exposes the existing artifact/version/term-source/link relationships through a bounded private definer and public invoker RPC, retaining current workspace membership/MFA checks and original-source identity. Existing table policies and immutable source records are unchanged. Compensation: revoke discovery function access without deleting history. Mounted API returns no-store exact-scope data and rejects stale/malformed responses.

### October 31 lifecycle metadata refresh

Before candidate72 SQL, read-only hosted queries confirmed latest ledger20261023221455 and no public acquisition_signature_reviews/acquisition_contract_transitions. Live deals still has its legacy primary key and buyer/profile/lead foreign keys; indexes include primary key, stage, closing date and one active lead. Its authenticated_full_access policy remains narrowed by require_approved_operator. The additive candidate stack supplies the scoped guards/RLS; production has not received it. Inspected local terms shape/protection and signature review/policy keys before extending canonical deals with an independent transition ledger. Candidate72 retains offer_made and nullable legacy signed fields for pending_signature, preserving every original terms version. Full72-migration populated rehearsal verified historical rows/definitions and Storage; evidence is in 2026-10-31-contract-lifecycle-result.json. No hosted schema change.

## Candidate74 — pending-signature document capture

No new entity/table. Reuses canonical deals and existing contract documents, upload reservations, retained Storage and audit history. CLI-created 20261101025323 extends only the current status guards in register_contract_document, admit_contract_document_upload and acquisition_evidence_object_access. Compensation: pause acquisition/upload activation and retain immutable history; do not delete evidence or reset contract status. Verified against the latest preceding definitions; no earlier security guard is replaced with a stale definition.

## Candidate75 — execution findings storage

`20261101030340_acquisition_execution_findings_storage.sql` adds nullable execution_findings to existing acquisition_contract_reviews and extends the private review-policy kind/purpose constraints. Existing tenant/reviewer/artifact/verification foreign keys, sequence uniqueness, RLS, grants and immutable trigger remain intact. Ordinary review rows require NULL findings; executed_contract approvals require the exact confirmed finding/term shape, while withdrawals require NULL. Policy provisioning remains private with no application grant. Existing generic review RPCs still reject executed_contract, preventing approval through the old payload/hash contract.

Inspected latest source definitions in 20261101000910 and 20261101010937 alongside immutable term/source constraints in 20261101004230. Fresh read-only hosted metadata confirms these candidate review tables remain absent and migration ledger remains 20261023221455. No production migration applied. Compensation: keep the execution write route unavailable or pause acquisition, retaining rows and audit history. Do not delete findings or downgrade status. Shape validation does not resolve source identities, scan authority or legal efficacy; those checks are mandatory in the forthcoming controlled writer/read path.

## Candidate76 — controlled execution-review writes

CLI-created 20261101030913 adds execution_sources to the existing immutable review table and a separate record_execution_review RPC. It leaves the old review RPC/hash contract unchanged. The new full-payload fingerprint includes findings, target/version, independent review sequence, exact note, actor and session. Source metadata is derived server-side from current references and signed scans, stored with original artifact/version/hash/purpose/scan identity and limiting deadline; clients cannot supply this journal. Existing table isolation, foreign keys, immutability and restricted grants remain intact. The public wrapper is invoker-only; its private definer requires current owner/admin MFA/session authority.

Fresh hosted inspection still shows ledger20261023221455 and absent candidate contract-review/version tables. No production migration or policy provisioning. Compensation: pause acquisition or revoke execution policy authority; retain historical approval/withdrawal rows, source journal and audit. There is no status advancement or signing effect. Current-state/discovery/UI integration, real gateway acceptance for the new mounted endpoint, and remaining lifecycle acceptance are still required.

## Candidate77 — current execution-review authority

CLI-created 20261101031709 adds read-only private execution_review_current and authenticated invoker-wrapped execution_review_state. No new table, grant expansion, policy provisioning or lifecycle mutation. Reads reuse the existing owner/admin MFA/session boundary. Current authority requires the latest exact executed_contract review, live reviewer/session/policy, current target terms/status, activation, unexpired original source journal, every original source reference and its exact saved scan. A newer scan does not replace the saved verification identity. Historical review rows and retry receipts stay unchanged after revocation. Fresh hosted metadata still shows ledger20261023221455 and absent acquisition review table; no production migration.

## Candidate78 — bounded execution review choices

CLI-created 20261101032437 adds read-only execution_review_candidate with a private definer and authenticated invoker wrapper. It reuses current-state authorization and retained document references, resolves the exact current scan and pre-existing reviewer policy, and bounds expiry by document retention, scanner/reviewer sessions, source-key scope, retention/reviewer policy and policy duration. No writes, new table or policy provisioning. Selected agreement identity is separate from the original withdrawal identity. Prepared terms are returned as preparation data, not confirmed returned-agreement facts; the writer still validates the final sourced findings independently. Fresh hosted ledger20261023221455, candidate review table absent; no production apply.

## Reviewed executed status — local candidate80

CLI-created `20261101034450_acquisition_executed_contract_transition.sql` extends the existing `acquisition_contract_transitions` entity, without adding a second lifecycle table. The original signature-release reference remains required on sequence1/draft→pending_signature. Sequence2/pending_signature→executed instead requires a workspace/contract/version/kind-bound `execution_review_id`; the composite FK only accepts `executed_contract` history. Existing SELECT RLS, grants and immutable-history trigger remain in force. `deals.acquisition_status` permits executed while the controlled trigger requires the corresponding immutable transition; legacy pipeline/title/buyer/money columns stay unchanged.

The existing controlled transition RPC preserves its argument/receipt and exact retry fingerprint. The new branch serializes contract history, locks every retained execution source and its retention/scanner/session authority, locks the reviewer policy and session, and re-evaluates the latest exact review plus complete matching terms after waits. A prior choice or client evidence cannot authorize the write. Status and one audit entry commit atomically. Original retries remain historical after pause/revocation; another request cannot reuse sequence2. No public raw-write grant or policy-provisioning path is added.

Hosted read-only verification on October31: migration ledger20261023221455; candidate transition/review tables absent. This migration is local only. Compensation is acquisition pause/current-policy revocation while preserving immutable status/history; corrective status paths require separate reviewed implementation. Do not delete a recorded execution or reset the deal to conceal an uncertain legal outcome. Guided executed-transition discovery/action is still pending; current read models retain executed contracts and hold unsupported subsequent actions.

## Guided executed-status choice — local candidate81

CLI-created `20261101035403_acquisition_executed_transition_choices.sql` replaces only the private read-only lifecycle choice function; existing authenticated invoker wrapper, grants, RLS and write endpoint remain unchanged. The draft choice preserves its signature-review identity. Awaiting-signature sequence1 requires the latest current execution review and returns a distinct `execution_review_id`; recorded executed sequence2 returns a hold with no candidate. Paused, changed-version and missing/revoked-review states never supply an action. Reads do not create reviews, provision policies, mutate lifecycle or authorize external transactions.

Backend/client discovery schemas distinguish the two evidence types and exact prior status/sequence. The existing guided status card uses the returned target for its explanation, personal confirmation and exact saved-request recovery. Executed contracts remain visible; old execution reviews can still be withdrawn from the original review card while new approvals there stay unavailable. Date-only terms, amendments, title/disposition transitions and full PRD acceptance remain separate unfinished work.

## Deadline interpretation storage — candidate82 (local, not applied)

CLI-created `20261101040743_acquisition_deadline_resolution_storage.sql` extends `public.acquisition_contract_reviews` with `deadline_term`, `deadline_resolution`, `deadline_original_review_id`, and generated `deadline_original_status`. Existing equivalent review parent, source-version mechanism, immutable trigger, SELECT RLS, restricted grants and shared kind sequence remain unchanged. Reviewed-policy kind/purpose constraints admit the new kind without seeding policies.

The original-approval foreign key binds workspace, contract, version, review kind, deadline term and approved status. The supporting unique constraint and partial latest-per-term index permit independent term withdrawal while preserving the shared ledger sequence. Shape constraints reject interpretations on unrelated review kinds, source identity/hash/version mismatches, replacement interpretations on withdrawal and missing original approvals. The private validator checks exact JSON keys, retained sources, named zone/local time/explicit offset, DST folds/gaps and calendar precision. It exposes no authenticated RPC.

Compensation: leave the review path disabled and preserve all history; later revoke policy authority or pause acquisition rather than erase records. No production migration is approved or executed. A controlled writer with locked original-term/source/policy validation, audit/idempotency, current-state discovery, execution-review binding and guided UI remains required. Focused disposable storage tests:4 passed20.215s. Full disposable rehearsal passed:81 migrations,26 access probes,212 workflows and114 actual PostgREST/API checks. Historical24 rows/22 populated tables/103 definitions and Storage fixtures preserved. Evidence:`evidence/2026-10-31-deadline-storage-result.json`. This is local acceptance, not hosted activation.

## Controlled deadline interpretation writer — candidate83

Adds `deadline_sources` to the existing review ledger, restricted to approved deadline interpretations with one or two bound originals; withdrawals and other review kinds require NULL. Both actual original-term source and proposed interpretation source are resolved and bound under locks. `record_deadline_resolution_review` follows existing authenticated invoker/private-definer architecture and preserves existing RLS/raw-write denial, original source foreign keys, exact retries, shared sequence and immutable audit history. No contract terms or lifecycle state are updated. Policy provisioning and production apply remain disabled/unapproved.

Compensation: preserve history and disable new reviews through the existing activation/policy controls; original withdrawals remain available under verified reviewer membership/session. No new API route consumes this writer yet. Focused five-case disposable SQL validation and the full82-migration/217-workflow/114-API-check disposable rehearsal passed. Historical rows/definitions and Storage fixtures were preserved. Evidence:`evidence/2026-10-31-deadline-write-result.json`.

## Deadline current-state reads — candidate85

CLI-created `20261101043729_acquisition_deadline_resolution_state.sql` adds no table or mutation path. The existing immutable review/term/source tables remain authoritative. `private.deadline_review_current(uuid,timestamptz)` is ungranted and validates exact latest-per-term evidence and authority. The scoped authenticated state wrapper additionally checks actual owner/admin MFA/session access before returning history, original precision, shared concurrency sequence and selected-term sequence. Existing RLS, grants and source indexes are unchanged.

Compensation: omit/disable the read UI if rollout fails; preserve all evidence and decisions. No production apply is approved. Six focused SQL cases and the full83-migration/223-workflow/119-API-check disposable rehearsal passed with historical rows/definitions and Storage preserved. Evidence:`evidence/2026-10-31-deadline-state-result.json`.

## Deadline action discovery — candidate86

`20261101044534_acquisition_deadline_resolution_choices.sql` adds only private-definer/public-invoker read functions. It reuses existing review, term-source, artifact, scan, policy and session records; table constraints/RLS/grants remain unchanged. Original source authority and selected interpretation source jointly bound readiness/expiry. The latest selected-term approval supplies original withdrawal identity, while the shared ledger maximum supplies the concurrency cursor. No new policy provisioning or execution authority.

Compensation: omit/disable the discovery UI while retaining sources and review history. Four focused SQL cases and the full84-migration/227-workflow/121-API-check disposable rehearsal passed, preserving historical records/definitions and Storage. Evidence:`evidence/2026-10-31-deadline-choice-result.json`.

## Execution deadline reference validation — candidate87

`20261101045444_acquisition_execution_deadline_binding.sql` replaces `private.valid_execution_findings` to admit an optional exact calendar-review reference list while preserving legacy five-field shapes. Adds ungranted `private.execution_findings_match` to compare source-bound dates through temporary derived instants. No tables, RLS policies, writer grants, source-journal bounds or execution transitions are changed. Current writer still holds calendar-only findings.

Compensation: retain legacy execution path and calendar hold; preserve references and original calendar terms. Five focused SQL cases pass; full upgrade/API rehearsal pending. Final integration must expand the source union to13 and add deadline reviewer/policy/source locking to execution review and transition before activation.


### Candidate88 — bound deadline execution authority

`20261101050425_acquisition_execution_deadline_authority.sql` reuses the existing contract/review/source/status tables and public RPC signatures. The sole constraint expansion permits1–13 execution source entries instead of1–7. Existing RLS, immutable triggers, unique identities, foreign keys and grants remain intact. A new private invoker locking helper has no public/anon/authenticated/service grant. Existing controlled private definer writers retain fixed empty search paths and actual workspace/session/MFA checks. No new parent records or policy seeds. Compensation: pause acquisition/revoke reviewed authority while retaining immutable historical findings and transitions; do not delete review history or silently reset a recorded status. Local verification is in progress; no production application authorized.


### Candidate92 — controlled title-review entry

`20261101052408_acquisition_title_review_transition.sql` extends existing `deals` and `acquisition_contract_transitions` check constraints to admit only the next recorded sequence3 edge. It reuses the existing execution-review foreign key, immutable status/audit ledger, source journals, deadline policies and RPC. Existing RLS, unique request identities, permissions and tenant boundaries remain unchanged. No new entity, index, policy seed or exposed definer is introduced. The private transition writer rechecks the exact previously recorded execution review under current original-source and reviewer/deadline authority. The deadline-current predicate permits the new lifecycle state without altering original calendar terms. Compensation: disable acquisition or revoke authority while retaining history; a controlled future exception is required to correct status. Production application remains unapproved.


### Candidate93 — title-review choice discovery

`20261101053450_acquisition_title_review_choices.sql` replaces only the existing private lifecycle-choice function. It retains fixed empty search_path, existing public invoker wrapper/permissions and owner/admin/session/MFA access from signature-review state. No table, constraint, index, grant, policy or new entity. Title entry is offered only for sequence2/current executed version with the exact current execution review retained by its recorded execution transition. Current review and expiry are checked again; discovery writes nothing and creates no authority. Sequence3/title_review reports started with no repeat action. Compensation: pause acquisition; retain source/status history. Read-only hosted refresh confirms ledger20261023221455 and absent candidate review/transition/choice objects; evidence2026-11-01-title-choice-catalog-check.json. Production apply remains unapproved.


### Candidate94 — original title-document capture

`20261101054305_acquisition_title_contract_documents.sql` replaces the existing registration, upload-admission and Storage object-access functions with the same signatures/privileges, adding current title_review to their status sets. It adds no table, index, policy, grant or new logical entity. All original version/purpose/source/hash/size/provenance, session/MFA/role/workspace, retention, shared upload-slot and object-operation checks remain. Registration retries return original immutable metadata after a hold; a historical receipt cannot bypass fresh upload or Storage authorization. Mail branches are unchanged. Compensation: pause uploads/acquisition or revoke retention authority while preserving source/audit history. The hosted read-only check still finds ledger20261023221455 and no candidate artifact/registration/admission objects; evidence2026-11-01-title-document-catalog-check.json. No production migration authorized.

### Candidate103 — internal purchase-path proposals

`deals` remains the canonical contract/disposition parent. `acquisition_disposition_plans` is an immutable child history, not a competing deal table. It binds existing contract versions and recorded executed/title-entry transitions using tenant-scoped composite foreign keys. The original proposal self-reference also retains exit type and both transition roots. Owner/admin membership, MFA and live session checks govern reads/writes; direct writes and service-role access are revoked. Existing buyer, contract price, gross fee, closing date and lifecycle fields are untouched.

Before SQL, inventoried the disposable current catalog: `evidence/2026-11-01-disposition-plan-local-catalog.json`. Migration `20261101071737_acquisition_disposition_plans.sql` is additive and passed local full-catalog validation (94 migrations,26 access checks,275 workflows,148 actual API checks). Forward compensation is pause or controlled personal withdrawal, preserving immutable history/audits. No production application approval. See `DISPOSITION-WORKFLOW.md` for the exact authority boundary and next guided app step.

### Candidate106 — post-execution disposition findings in the existing review ledger

Pre-SQL disposable catalog inventory: `evidence/2026-11-01-disposition-findings-local-catalog.json` (130 columns,86 constraints,22 indexes,10 policies,6 relation-security records). Inspected actual composite foreign keys, original-version/generated columns, review-kind/purpose/status checks, indexes, RLS and grants across deals, versions, policies, reviews, transitions and proposals. Existing review SELECT requires actual owner/admin membership and MFA; direct writes/service-role grants remain unavailable.

Migration `20261101074125_acquisition_disposition_findings_storage.sql` extends `acquisition_contract_reviews` with distinct `disposition_findings`, source journal and original proposal/exit/execution/title-entry/title-decision references. It extends the existing policy kind/purpose checks without inserting a policy. Composite foreign keys preserve workspace, version, exit and recorded roots. An approval must reference an approved title decision; held findings may reference an approved or held title decision. Original withdrawal preserves the exact proposal, exit, execution, title entry and title decision/status. Findings/journals never attach to another review kind. Existing source/policy FKs, RLS, restricted grants and immutable triggers are preserved.

No application writer or transition is enabled. Storage-level reference consistency is not proof that a referenced approval is current; the upcoming controlled writer/state service must validate current authority and latest histories under locks. Compensation: keep this path unavailable or pause acquisition, retain immutable review/audit history, and use future controlled withdrawal when available. Production application remains unapproved.

### Candidate107 — original disposition source resolution

Inventoried candidate106 before SQL: `evidence/2026-11-01-disposition-source-local-catalog.json` (142 columns,91 constraints,23 indexes,10 policies,6 security records). Reviewed the exact original-proposal/title/withdrawal FKs and unchanged review/proposal RLS/grants. Existing current-source/reference/lock helpers were inspected before reuse.

Migration `20261101074845_acquisition_disposition_source_resolution.sql` adds only an ungranted private invoker function. It derives the purchase-contract root and original scan from the current proposal's recorded execution, requires satisfactory contract-interest/assignment-provisions findings to cite that original, and retains all other source versions and exact bytes through existing references. It locks current source authority and rechecks it after waits. No record entity, direct write grant, public RPC, policy provisioning or transition is introduced. Forward compensation is to leave the forthcoming writer disabled; retain all existing records. Current disposition approval remains the responsibility of the forthcoming controlled writer/state service.
