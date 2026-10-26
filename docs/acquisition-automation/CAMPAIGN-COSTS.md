# Campaign cost evidence and coverage

Status: deterministic calculation implemented; persistent evidence ingestion, authenticated API and dashboard remain pending. This is not completed FB-006 or live spend reporting.

`tools/acquisition_costs.py` projects a single workspace/campaign, inclusive 1–366-day reporting window, explicit account reporting timezone, currency and observation cutoff. It does not fetch Meta, authenticate evidence, write records, authorize spend or derive costs from a planned budget. The eventual repository adapter must enforce membership, approved campaign/account association, evidence provenance and completeness before invoking it. A caller-supplied hash or complete flag is not proof of provider authenticity.

## Evidence contract

Each daily revision supplies canonical UUID `id`, `workspace_id`, `campaign_id`, ISO `date`, positive integer ledger `revision`, exact IANA `reporting_timezone`, `currency`, integer `amount_minor`, `coverage`, timezone-bearing `observed_at`, access-controlled `evidence_ref` and lowercase SHA-256 `evidence_hash`.

Initial supported currency is USD, with two minor-unit decimals. Other currencies are explicitly rejected; there is no implicit foreign-exchange conversion. Input amounts must be exact nonnegative integers, not booleans, floats or numeric strings; maximum is 100 trillion cents per daily observation. Output monetary values are decimal integer strings to preserve precision in JavaScript. This projection does not imply support for credits/refunds as negative spend: any such provider evidence requires reconciliation before ingestion.

Coverage is complete, partial or withdrawn. Withdrawn requires null amount. Missing dates remain missing and null. A complete daily observation must occur after the end of the account's local day, including daylight-saving boundaries, and no observation can occur after the supplied report cutoff. Adapter queries must select only evidence within the requested window and cutoff; mixed scopes, currencies, timezones or outside-window evidence reject the projection rather than silently disappear.

The highest ledger revision per date wins, independent of input order and observation timestamp. A newer partial or withdrawn observation invalidates the old complete total; the projection never falls back to stale spend. Exact duplicate rows are idempotent. A conflicting UUID or duplicate day/revision under another UUID rejects the batch. Maximum input is 10,000 rows; a repository adapter must detect truncation and refuse a report rather than passing an incomplete batch.

## Reporting semantics

`total_cost_minor` is available only when every requested day has complete evidence. `observed_cost_minor` sums the known latest amounts, including partial amounts, and is explicitly not the reporting-window total. When there are no known amounts it remains null; an explicit evidenced zero remains zero. Per-day output retains selected revision ID, sequence, hash and normalized observation timestamp without exposing storage references or raw provider payloads.

CPL and qualified CPL remain null with `denominator_status=NOT_RECONCILED`. Before those metrics can be computed, the implementation must establish matching time-window/account/campaign coverage, UTC-to-account-local inquiry timestamps, current attribution, duplicate identity treatment and funnel stage provenance. Inquiry touches are not unique sellers or closed transactions. No contract/close conversion can be inferred from an offer amount approval.

## Next implementation boundaries

Inventory current cost/insight equivalents and deployed catalog before additive SQL. Extend existing equivalents where possible. Persist immutable observations and revisions with composite workspace constraints, RLS, controlled writes, audit events, provider-event idempotency and private evidence retention. Keep provider collection disabled until approved account identity and credentials are validated. Resolve current campaign review authority when reporting; a stale campaign link cannot silently authorize costs against another campaign. Add authenticated coverage read APIs and unavailable/partial/complete UI, followed by reconciled funnel metrics. No production migration without approval.

Tests cover exact amounts, unknown versus zero, partial coverage, superseding withdrawals, replay/conflicts, scope/unit mismatch, bounds, malformed evidence, local-midnight/DST boundaries and report cutoffs. No database or provider transport is used by these tests.


## Verified persistence target and fixture

The October 26 catalog refresh found existing `fb_campaign_performance`; the planned daily evidence persistence will extend it. See SCHEMA-MAPPING.md for campaign-master conflicts, generated CPL/default-zero semantics and legacy access paths. `scripts/acquisition_campaign_fixture.py` now restores this table and its fb_campaigns/fb_ad_sets parents before boundary migrations, using metadata captured from production. It preserves actual types, generated expressions, parent keys, grants, policies, triggers and non-constraint indexes. This is disposable test setup, not a production migration.

Focused tests demonstrate legacy CPL calculation, duplicate-key rejection, child FK denial, parent cascades, mutable legacy spend, default zero, separate acquisition-only access denial and the baseline TRUNCATE grant. These tests deliberately preserve the observed old behavior so the upcoming extension must explicitly enforce new-row isolation and immutability without claiming old data already has reviewed cost provenance. The source catalog has three parent tables only; unrelated Facebook audience/lead tables and full production-schema upgrade remain separate coverage.

RLS/grant implementation reference checked during this inventory: https://supabase.com/docs/guides/database/postgres/row-level-security . Policies do not remove table grants, and mutation protections must include non-row operations where applicable.
