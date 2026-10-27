# Campaign cost evidence and coverage

Status: deterministic calculation, reviewed-import SQL persistence and authenticated coverage read API implemented; provider ingestion and dashboard remain pending. This is not completed FB-006 or live spend reporting.

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


## Implemented reviewed-import ledger and read API

CLI-created `20261026234504_acquisition_cost_evidence.sql` extends `fb_campaign_performance` in place. Legacy columns, rows, generated CPL and existing FK identities remain intact. Acquisition evidence adds workspace/campaign/review keys, sequence, exact minor units, coverage, account timezone, observation/recording timestamps, original request, reviewer and audit. Composite tenant FKs point to the existing acquisition campaign master and reviewed link. Legacy foreign IDs and metrics must all be null on acquisition rows; the generated legacy CPL is therefore null.

The restrictive acquisition namespace policy excludes evidence rows from direct authenticated table reads/writes, including legacy command-center aggregates. Scoped owner/admin/operator reads use a private definer function through a public invoker wrapper. Controlled writes require owner/admin, MFA, a live approved profile/session/membership, active workspace and a current exact campaign/account link. Global campaign-link locking serializes writes with revocation; actor/integration/campaign row locks preserve checked authority through commit. Request and campaign locks serialize retries and revision ordering. TRUNCATE/TRIGGER grants are removed, and scoped row updates/deletes or service-role inserts are rejected by the trigger. Legacy rows retain their existing permitted behavior.

`record_acquisition_cost(id, workspace, link_review, data)` accepts exactly date, amount_minor, coverage, currency, reporting_timezone, observed_at, external_campaign_id, ad_account_id, evidence_ref, evidence_hash and expected_revision. The review derives the internal campaign. The first evidence fixes its external campaign/account/timezone identity; subsequent revisions cannot silently change that identity. Correcting an account/calendar requires a separately reviewed campaign or a reviewed compensating migration, not overwriting evidence. Exact same-actor request retries return the historical saved result even after link revocation; new records require current attribution. New writes receive one immutable audit. A hash/reference supplied in this explicitly reviewed import is not cryptographic proof that Meta sent the data; the reviewer must verify the source artifact. The migration enables no provider import worker. The authenticated HTTP import contract added subsequently is documented below.

`acquisition_cost_evidence(workspace,campaign,start,end,as_of)` returns at most one latest recorded revision per requested day (maximum 366), with current campaign-attribution validity. Both observed_at and recorded_at must be at or before the cutoff. Current attribution is checked now, not historically reconstructed as of that cutoff. Raw artifact references and original requests are not exposed: scoped record references identify persisted evidence. Account timezone remains unknown until evidence exists. Original historical cost evidence is retained when a link becomes invalid; it is not silently reassigned.

GET `/api/acquisition/workspaces/{workspace}/campaigns/{campaign}/cost-coverage?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&as_of=<optional aware timestamp>` forwards the user JWT, validates the evidence envelope and invokes the deterministic calculator. Unknown timezone yields unavailable with null totals. Any selected stale campaign attribution makes status requires_review and suppresses window/observed totals, while per-day historical amounts retain explicit attribution_current and link_review_id. Gaps remain incomplete and CPL stays null. Returned cost amounts are decimal minor-unit strings. This route does not fetch provider data or send any campaign action.

Compensation: keep acquisition routes/activation disabled if a release must be held; revoke affected campaign links to prevent new cost writes and mark related reporting stale. Preserve evidence, review and audit history. Corrections append partial/withdrawn/replacement revisions under a current reviewed link. Do not drop the table, replay old migrations or restore broad mutation grants. A forward compensating migration is required for any schema rollback, with populated legacy/evidence preservation tests and separate production approval. Full production-schema upgrade/PostgREST/provider acceptance remain gates.


## Authenticated reviewed-import HTTP contract

POST `/api/acquisition/workspaces/{workspace}/cost-evidence` accepts `{id, link_review_id, reviewed: true, data}`. `data` contains exactly the eleven ledger input fields listed above. The caller must supply an exact request UUID and current link review; internal campaign and actor are derived server-side. No client workspace, campaign override, actor, revision result or authority field is accepted in the body.

The API requires strict integer minor units/revision, canonical calendar date, an explicit timezone-bearing observation string (at most six fractional second digits), supported account timezone, USD, numeric-string provider/account IDs, evidence reference and SHA-256 format. It rejects future observations, incomplete local days marked complete, non-null withdrawn amounts and null amounts for complete/partial evidence. An explicit strict boolean review acknowledgment is required. This acknowledges human review of an existing source artifact; it does not claim the API fetched or cryptographically authenticated Meta data. Automated account-scoped provider retrieval remains outstanding.

The user JWT is forwarded to the existing controlled SQL write. The API validates the returned request ID, exact next revision, canonical campaign UUID, duplicate boolean and false execution authority before reporting success, and returns only those five fields. A malformed reply is 502/unconfirmed; transport failure remains 503. Neither causes an automatic mutation retry. Clients must retain the original UUID, review and complete payload for reconciliation, including after reload. A retry with altered evidence conflicts. A confirmed duplicate after revocation establishes only that the historical revision exists, not that its attribution is current. Refresh cost coverage separately before presenting totals.

Owner/admin, MFA, active workspace and live session/role checks remain database-enforced. Unknown or forbidden fields and invalid data fail before database mutation. Feature-disabled requests use the existing acquisition route gate. A dashboard and user-facing artifact review/import experience remain pending; this API does not collect credentials, upload evidence, activate campaigns or incur spending.


## Dashboard coverage view (October 26)

Facebook draft cards expose an on-demand cost panel. A user selects an inclusive 1–366 day account-calendar window; the panel uses the scoped coverage endpoint and validates the full projection before displaying amounts. BigInt formatting preserves exact USD minor units. Unknown reporting timezone stays unavailable, missing/withdrawn days remain unavailable, partial observed totals are labeled, and revoked attribution suppresses totals while retaining clearly historical daily evidence. CPL stays unavailable pending denominator reconciliation. Editing dates or failed refresh hides previous results.

Coverage view is read-only. Reviewed import entry, artifact upload/retention, provider-authenticated collection and conversion reconciliation remain separate work. Frontend validation is presentation defense; database membership and immutable evidence rules remain authoritative. Synthetic browser evidence is in `evidence/2026-10-26-campaign-costs-mobile.jpg`.


## Client import recovery contract

`frontend/src/lib/costImport.ts` validates exact reviewed payloads, parses decimal USD without floating-point arithmetic and saves the complete request in user/workspace/campaign-scoped session storage before sending. Unknown outcomes, malformed replies and rejected retries retain that payload. A different payload cannot replace it through the helper. Confirmed matching responses clear only the identical stored request. This is tab recovery, not server persistence or proof of evidence authenticity. New submissions also validate future timestamps and complete account-local reporting days; the server rechecks all authority and revision constraints.

The entry UI is not connected yet. It must derive campaign/account/review from current reviewed attribution, fetch the daily revision rather than ask the user to invent it, keep pending requests immutable, and offer reconciliation for rejected and uncertain outcomes without silently discarding evidence.


## Reviewed entry form

`CostEntry` is embedded in campaign attribution review. Validated current campaign/account/review identities are supplied by the parent; all are reread before preparing and recording. Daily coverage supplies the expected ledger revision and established account timezone. The reviewer sees date, coverage, exact amount, next revision, account, campaign review, observation time, artifact reference/hash and request UUID before acknowledging. Editing clears that preview; concurrent daily/review changes reject the prepared write. Withdrawal records null amount explicitly.

Pending requests lock adjacent attribution and intake mutations. A scoped per-intake pointer restores the exact campaign request, including after revocation, and a second inquiry cannot overwrite the same campaign pending payload. SQL still controls all writes; presentation membership is not authority. Component and regression tests pass, but browser and real PostgREST/MFA acceptance are outstanding. The next recovery work must safely release definitively rejected fresh attempts while preserving any earlier uncertain result.


## Confirmed rejection recovery

The cost endpoint emits `X-Acquisition-Cost-Rejected: true` only for mapped 401/403/409 errors from its transactional persistence call. The client accepts this marker only on the matching POST route and status. A first attempted request may be released only when its saved payload still exactly matches. Any prior uncertain attempt makes a later rejection insufficient to clear it. Network failures, malformed replies, generic error codes and changed storage remain pending. Fresh confirmed rejection resets preview/acknowledgment so the reviewer must prepare from current evidence again. Validation/dependency errors without this marker remain conservative; no blanket discard action exists.
