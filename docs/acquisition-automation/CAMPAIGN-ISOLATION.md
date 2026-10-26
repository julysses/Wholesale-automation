# Existing campaign isolation: inspected baseline and migration requirements

## Verified October 26, 2026

Read-only catalog queries against `dvzhzlipbwzzcliujzyz` inspected `ad_campaigns`, `ad_creatives`, `lead_form_configs` and `lead_form_submissions`, inbound foreign keys, policies, indexes, triggers, grants and migration history. No production DDL/DML or customer rows were read. Evidence is `evidence/2026-10-26-campaign-catalog.json`: 70 columns, 14 constraints, nine policies, three triggers, and 95 applied migration entries; latest recorded version remains `20261023221455_retell_recovery_production_guard`.

`ad_campaigns` remains the canonical acquisition campaign table. There is no deployed workspace ownership column, currency field or unique external-campaign index. Its `cpl` is a stored generated numeric column; `total_spend`, counts and status have legacy zero/active defaults. Those defaults cannot establish acquisition spend coverage or approval.

Approved authenticated users currently have broad campaign/creative/form policies. Active forms have an anonymous SELECT policy. Campaign, creative and form grants include TRUNCATE for application roles, which RLS does not filter. Existing acquisition migrations add a restrictive legacy boundary to these tables when present, but do not yet assign workspace campaign ownership. No claim of deployed tenant isolation is made for these legacy tables.

Foreign-key dependencies include:

- Campaign -> creatives (delete cascade), form configurations, and leads.
- Creative -> leads.
- Form configuration -> submissions.
- Submission -> leads, Retell form SMS jobs and SMS resubscription reviews.

Current database functions referencing campaign/form configuration include `finalize_form_submission` and `launch_monitor_snapshot`. The former is a service-role finalization path; it must not become a way to associate shared/public forms with scoped campaign data. The latter remains a release-health read dependency.

## Application paths requiring coordinated protection

`web/api/lead_forms_api.py` lists, creates, patches and synchronizes campaigns; lists/changes creatives and form configuration; and computes shared KPI/AI optimization inputs. Campaign PATCH accepts a dictionary. `web/api/webhooks.py` also resolves a campaign by external ID for the legacy Facebook flow. Protect these paths from scoped campaign data before populating workspace-owned records. Existing user-token handling and database restrictions must remain decisive; an application filter alone is insufficient for service-role writes.

## Required migration behavior

1. Extend `ad_campaigns`, retaining IDs and legacy rows. Workspace ownership must be immutable once assigned. New acquisition campaigns start explicitly draft, with no publish/fund/transport side effect. Budget cents and currency must have explicit semantics distinct from legacy numeric fields; unknown observed spend stays unknown.
2. Use scoped authenticated read policies and controlled private SECURITY DEFINER mutations with public INVOKER wrappers, fresh role/session checks, immutable audit and idempotent requests. Revoke truncate paths, including cascade dependencies. Retain appropriate legacy access only for unscoped records.
3. Protect child tables and all parent-association writes, including direct service-role writes, public form reads, lead associations and legacy finalization. Reject mixed workspace relationships. Enrollment of an existing campaign requires a complete dependency review; do not silently acquire unrelated lead/form/creative records.
4. External provider links require reviewed evidence and explicit account/workspace identity. Do not match names or infer ownership from an external ID. Reject competing active mappings; keep correction/revocation history. Receipt retries must resolve the same source/campaign relationship.
5. Use additive multi-touch source/event relations over existing lead/intake/provider receipts; do not create another campaign master or overwrite earlier attribution. Cost data requires source/account, date/window, currency, coverage and revision semantics before CPL or conversion reporting.
6. Prove legacy sentinels survive; cross-workspace and limited-role reads/writes fail; public forms cannot reveal scoped campaign data; service-role/legacy RPC bypasses fail; exact request races deduplicate; revoke/correction invalidates current mappings without deleting history.

Compensation will hold acquisition gates/provider links, retaining immutable campaign/source history. A production migration still requires separate approval after disposable populated-upgrade and RLS acceptance. No campaign enrollment or schema migration has been executed by this audit.

## Disposable fixture coverage

`scripts/acquisition_campaign_fixture.py` reconstructs the three missing parent tables from the inspected catalog, including exact numeric widths, generated CPL expressions, captured policies/grants/triggers and campaign-related foreign keys to existing lead/submission fixture tables. It runs before acquisition boundary migrations so their catalog scans actually include campaigns, creatives and form configuration.

The two fixture tests verify generated CPL/non-overridability, parent delete protection and creative cascade, four restored foreign-key edges, current shared approved-user visibility, public active-form behavior and acquisition-only account restriction. They deliberately document the baseline privilege gap; they do not claim to fix it. Full Retell/SMS job dependencies and the complete production schema remain outside this focused fixture. The planned campaign isolation migration must add acceptance tests that require the stricter intended behavior.

Validation completed: the ten integrated journeys passed with expanded dependencies. The full 106-case PostgreSQL run passed 102 cases and identified four website-consent fixtures missing form parents. Those fixtures now create inactive synthetic form configurations; all four cases passed on targeted rerun. Production foreign keys were preserved. The initial catalog restore ordering was also corrected to create primary/unique constraints before foreign keys.

## Implemented ownership increment

CLI migration `20261026205233_acquisition_campaign_ownership.sql` extends `ad_campaigns` rather than adding another campaign master. New workspace-owned records contain an acquisition channel, nonnegative USD budget in cents and creator. The dedicated owner/admin RPC checks live approved session/membership, active workspace and activation under locks. Concurrent identical request UUIDs create one draft and audit event; conflicting identity or inputs fail. No legacy row is automatically enrolled. Observed spend/counts and daily budget are explicitly null, not legacy default zero; external campaign ID is also null.

Authenticated reads of scoped records require actual owner/admin/operator membership. Unscoped records retain the prior legacy approval boundary. Controlled creation is the only acquisition write currently available: direct updates, deletion, workspace removal/reassignment and service-role inserts are denied. Truncate and trigger privileges on campaign/creative/form tables are revoked for application roles. Child association guards check visible parent rows under locks and reject scoped campaign references from legacy leads, creatives or form configurations, including privileged finalization calls. No public form can be attached to these scoped drafts through current application paths. Existing-campaign enrollment and controlled child association are intentionally not yet exposed; those require the reviewed dependency workflow described above.

POST `/api/acquisition/workspaces/{workspace}/campaigns` accepts request UUID, name, channel, integer `budget_cents` and explicit `currency=USD`. Status, creator and execution authority cannot be supplied. GET on the same path returns bounded UUID-cursor pages of workspace campaign metadata through user-token RLS.

The shared lead-generation list, KPI and optimization routes filter out workspace-owned campaigns independently of the feature flag, using returned row metadata so they also work against the old schema. Shared PATCH and Facebook sync refuse scoped records before mutation/provider access. This protects flag rollback after scoped records exist. Database controls remain authoritative; application filtering is not the only protection.

Validation includes five focused PostgreSQL cases, three final database regressions, 142 API/legacy/public-form/Retell form-SMS cases and eleven integrated SQL journeys. Tests prove concurrent idempotence, unknown observed costs, scoped reads, operator write denial, expired session/activation rejection, raw-service denial, forbidden parent associations and preserved legacy foreign-key behavior. Provider traffic is synthetic; no production migration was run. The complete populated production-schema upgrade and actual PostgREST acceptance remain release requirements.

Compensation: keep acquisition activation and provider routes disabled, preserve draft rows and audit history, and retain the new access controls. Do not drop ownership columns or remove restrictive policies to roll back a UI feature: that would expose scoped rows through shared paths. Restore the application version only with shared-campaign exclusion retained. No destructive down migration is provided. Controlled amendment/cancellation, reviewed external account mapping, source links, cost observations and reporting remain to be implemented.

Reference checked during implementation: [Supabase RLS and grants](https://supabase.com/docs/guides/database/postgres/row-level-security). The migration combines restrictive policies with explicit grants and mutation guards because service-role access bypasses RLS.

## Draft dashboard

`CampaignDrafts.tsx` is available inside the existing feature-gated acquisition review page. It lists only validated workspace drafts, shows planned USD budgets separately from unknown observed spend, and exposes creation to current owner/admin members. The database checks fresh authority at execution. Future-channel draft metadata does not activate those channels.

Dollar entry converts decimal digits directly to integer cents, rejecting negative, exponential, excessive precision and out-of-range values. Response checks bind the returned UUID, workspace, channel, budget, currency and draft status and require `execution_authorized=false`.

Before sending, the panel saves its exact request in browser tab session storage under a user/workspace key. Lost replies, mismatched results and later retry rejections retain that original request. Reloading the tab restores reconciliation; changing workspaces is disabled while unresolved. A definitive first-attempt rejection clears it. Storage failure before sending prevents the mutation; unreadable saved requests block new creation. This browser recovery state is not an audit record or server authority. Tab closure removes it, so reconcile saved drafts before recreating an unresolved request after closing the tab. No credentials or seller data are stored by this panel.

Validated through component tests, the full 243-test frontend suite, a feature-enabled build and lint baseline. Rendered browser/live API acceptance remains pending. Campaign linking, amendments and activation are not implemented by this UI.

## Reviewed Facebook campaign links

Migration `20261026214412_acquisition_campaign_links.sql` adds `acquisition_campaign_links`, an immutable review ledger, not another campaign master. It references the existing workspace campaign, inquiry and private integration using composite tenant keys. Authenticated owner/admin/operator reads use RLS; application roles, including service_role, have no direct mutation/truncate grants. Private DEFINER functions with public INVOKER wrappers govern review and current-state projection.

The review starts from an immutable seller intake. Its receipt resolves the configured Facebook Page integration; provider retrieval evidence supplies the external campaign ID. Missing/non-string/mismatched campaign identity fails closed. The reviewer supplies a numeric ad-account ID, independent ownership evidence reference and review note. This records a human-reviewed ownership assertion, not proof that Meta has verified that ad account. The configured Page account ID is explicitly returned as `page_id` and never reused as the ad-account ID.

POST `/api/acquisition/workspaces/{workspace}/intakes/{intake}/campaign-link-reviews` accepts request UUID, expected sequence, preparation hash, `link`/`revoke`, optional campaign/ad-account targets and mandatory evidence/note. GET `.../campaign-link-state` returns the derived Page/external campaign, latest review, sequence and current-link status. No actor, integration or external-campaign override is accepted. An owner/admin with MFA and a live approved session must review; the database locks workspace, membership/profile/session, source receipt/integration and campaign through commit. Global external-ID and request locks serialize retries and competing Page claims. An existing unreconciled link must be revoked before correction, even if its reviewer is no longer current. Revocation needs no active acquisition/integration gate.

Current status requires acquisition activation, enabled integration with the recorded approval reference, active workspace and approved reviewer membership with the original membership generation. A new review is required after membership changes. Integration enablement is evaluated as a current operational gate; temporarily disabling and restoring the same approval reference can restore operational validity. Historical entries remain unchanged. Exact-request retries can confirm the historical review even when a gate later closes; consumers must use current-state projection for current attribution.

The global external-campaign claim fence is conservative: another Page/workspace cannot claim the external campaign until the original claim is explicitly revoked. Cross-workspace transfer has no automatic shortcut. Campaign master/provider routing fields and lead associations remain untouched. This increment does not enroll old campaigns, publish/fund ads, verify provider account access, bind intake sources automatically or calculate costs. All responses explicitly deny execution authority.

Validation: concurrent SQL review races, competing Page claims, revocation while held, correction/history, tenant-target denial, missing evidence, MFA/live authority, direct service-role/immutable-write denial; API input contracts and a real-SQL HTTP journey with a lost post-commit reply. The 12 integrated journeys passed. Full production upgrade and actual PostgREST/provider acceptance remain pending.

Compensation: hold acquisition/integration gates and preserve the ledger. Use reviewed revocation for incorrect mappings. Do not delete history or remove workspace controls. This migration has only run on disposable local databases; production requires separate approval.
