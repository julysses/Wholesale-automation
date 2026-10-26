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
