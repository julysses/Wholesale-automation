## Latest — complete buyer reads on the full upgrade

The same thirteen migration apply/rollback and historical/access checks pass, plus
CSV/land imports, batch scoring, pinned call/SMS contention and all ten intake
journeys (123.53 seconds). New real-SQL buyer checks prove 1,003 buyers/history rows
through a 200-row response cap, a late best match and inactive-buyer exclusion.
Backend 1,340/10 skipped; frontend 289/58 files; build/typecheck and lint gate pass
with 143 existing findings. See `BUYER-READ-COMPLETENESS.md` for remaining buyer
import/background-result and operator gates. No production changes.

## Latest — durable 25-lead AI batches and operator recovery

The thirteenth unapplied proposal now adds private batch evidence, current progress
and explicit continuation. Real-SQL multi-batch and original-request replay checks
pass. See `CSV-BATCH-RECOVERY.md` and final result JSON for exact scope/timing.
Earlier checkpoint descriptions below are historical. No production changes.

## Current candidate — connected CSV intake, thirteen migrations

Main CSV API/UI now use the atomic transaction and one-way optional AI claims/results.
The existing thirteenth proposed migration is expanded, not applied in production.
Full apply/rollback/history/access, CSV data and connected API/scoring, land import,
pinned call/SMS overlap and ten intake journeys pass (125.82 seconds). Backend
1,325/10 skipped; frontend 262/54 files; build/typecheck/lint gate pass with 143
existing findings. Lost SQL acknowledgment is exercised after data, claim and result
commits; no repeated model dispatch. See `CSV-LEAD-TRANSACTION.md`. Large AI execution
and partial-batch recovery, signed-in operator acceptance and live launch gates remain.

## Earlier October 22 checkpoint — thirteen-migration foundation only

The main CSV database transaction foundation adds
`20261022170346_integration_csv_lead_intake.sql` to the explicit allowlist.
It verifies approved configured ownership, linked due tasks, immutable replay,
existing-work preservation, normalization, large batches and eight-session
manual-upload overlap. The new API/UI and optional AI dispatch are not connected;
R8 remains open. See `CSV-LEAD-TRANSACTION.md` and current result JSON.

## Current candidate — twelve migrations

The original eleven-file rehearsal is historical evidence. The October 22 manual
land import repair adds one new forward migration, making twelve in the current
explicit allowlist. Full apply, partial failure rollback, historical preservation,
manual import/API/eight-session deduplication, pinned call/SMS overlap and ten intake
journeys pass (123.14 seconds). See `MANUAL-LAND-IMPORT.md` and current result JSON.

# October 21 production-shaped integration rehearsal

Status: eleven-file schema composition and protected intake journeys passed locally. PR #21 remains draft; full integration readiness and production rollout are not certified.

## Exact checkout

`/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/integration`, branch `codex/wholesale-integration-review`, starting HEAD `27d233be489af0e256693dcfa1c2c7ee25656aa6`. Cloned the existing October 20 checkout with history; pulled upstream before changes. Origin is julysses/Wholesale-automation. Branch remains explicitly excluded from Vercel deployment; checkpoint commits use `[skip ci]`.

## Implemented verification

Ported the catalog restoration and Facebook migration rehearsal from the released candidate, including its test adapter correction for parameter-free SQL containing percent signs. Ported its service_role journey fixture, required form name, real acknowledgment delay and separate privileged audit connection. No application runtime or migration SQL was changed.

New command:

```sh
.venv/bin/python scripts/run_offline_tests.py --production-upgrade
```

The clean-environment runner creates a disposable localhost PostgreSQL database with synthetic owner/history, restores the saved catalog, rehearses the released Facebook migration, then applies only the eleven files in `forward-migration-order.json`. It first rolls the complete sequence back and compares data/functions, then commits locally, verifies unchanged historical rows and migration history, protected functions, restricted browser invocation and scheduler pauses. It finally executes the ten connected API/SQL lead journeys against the upgraded schema with provider boundaries mocked. It shuts down and removes the database in `finally`.

## Verified results

- Saved catalog restored: 100 tables, 120 functions, 384 constraints, 27 triggers and 127 policies; zero production rows copied.
- Facebook migration rehearsal passed its existing eight-worker contention and evidence-preservation checks.
- All eleven feature migrations applied and complete transaction rollback passed.
- Existing table columns/rows, including seeded held website jobs, SMS outcomes, native receipt, sessions/turns and email evidence, remained unchanged.
- Existing function changes are limited to `scan_list_pipeline()` composition and the intended old call-claim EXECUTE revocation. The old call function body remains unchanged; service_role can execute the new versioned claim and cannot execute the old one.
- New functions were checked for effective browser invocation: EXECUTE plus schema USAGE, excluding trigger-only entry points. A first overly broad assertion flagged a trigger helper; distinguishing trigger-only functions and private schema access resolved the harness mismatch without changing grants or weakening application security.
- Both SMS scheduler flags and all synthetic cron rows remain disabled; no network extension requests were recorded; empty-session recovery remains absent.
- All ten post-upgrade journeys passed (122.04 seconds): Hilltop, Jays and native Facebook acknowledgment/reply/receipts/STOP/no-replay, missing consent, missing-owner recovery and lost native receipt-response retry.

Machine-readable evidence: `production-upgrade-result.json`. Raw log: `logs/friday-production-upgrade-populated.log` (local ignored file). Migration hashes are recorded in the result.

## Limits and next work

This uses the saved October 20 catalog plus the separately released Facebook migration, not a fresh complete production export. It uses synthetic history and stubbed Auth/network/cron facilities. Populated compatibility fixtures now cover land, valuation and four historical call statuses; Real PostgreSQL offer/lot/valuation, trace-budget, scoring and restricted-ingress concurrency now pass using separate minimal fixtures. Full pinned-call/SMS overlap now passes; requirement-by-requirement R1–R12 acceptance remains open. An injected SQL failure after migration six now proves rollback of partial DDL, functions and retained rows. Production-volume lock behavior remains unproven.

Next: run feature concurrency under isolated ingress, compare relevant catalog drift, and review the exact schema/runtime release boundary. Do not deploy this branch, apply these migrations, activate collection or messaging, or replay held work on the basis of this evidence. Full Friday launch remains dependent on live controlled delivery and operator acceptance as well as the chosen integrated feature set.

## October 21 receipt concurrency fix

The populated upgrade run exposed a PostgreSQL 23505 race on the secondary
`facebook_lead_submissions_lead_id_key` during eight concurrent identical deliveries.
The real-SQL adapter used INSERT ON CONFLICT(id) DO NOTHING; it did not suppress
secondary uniqueness failures. Receipt persistence now catches only 23505, reads
by the deterministic receipt ID, and retains all immutable identity and consent
comparisons. Missing or conflicting receipts still fail; other database errors
propagate. No consent, DNC or held-session protection was relaxed.

Eight deterministic regression cases cover PostgREST and psycopg error attributes,
identical evidence, conflicting evidence, absent receipt and unrelated errors.
Six failed before the fix; all eight pass after it. The 36 focused native intake
checks pass. Full release backend: 1,139 passed, 10 skipped; full integration
backend: 1,269 passed, 10 skipped. Local PostgreSQL eight-worker contention passes.
These changes are candidate code only, not deployed production fixes.

Additional fixtures preserve one land lead, a valuation with radius 1.25, and four call requests (submitting, accepted, unknown, completed), using distinct synthetic contacts. Initial fixture setup errors (duplicate unresolved phone and missing required city) were corrected without modifying production constraints.

Final populated rehearsal: all ten post-upgrade intake journeys passed in 122.04 seconds; zero provider calls.

## October 22 dependency verification

Installed locked frontend dependencies with lifecycle scripts disabled. The initial
audit reported four findings (two high, two moderate). Compatible updates changed
Vite 6.4.3 to 6.4.5 and follow-redirects 1.16.0 to 1.16.1; the pinned Vitest and
its matched packages changed 4.1.11 to 4.1.12. Installation audits report zero
vulnerabilities afterward. No force upgrade or major-version change was used.

Both branches use identical package manifests and lockfiles. After the updates:
release frontend 179/179 tests, integration frontend 240/240 tests; both typecheck
and production build pass. Lint gates pass with existing debt unchanged (release
147, integration 144). Existing bundle-size warnings remain. These are candidate
changes; production deployment was not changed.

## October 22 feature concurrency

The clean-environment `pipeline/integration/run_local.py` run passed all nine
reported acceptance groups with Deno 2.9.6 and a disposable TLS PostgreSQL cluster.
It verified separate database sessions actually waiting on the same locks before
release. Coverage includes ingress duplicate/lost-ack/conflict/expiry/source and
restricted-role checks; competing offer approvals and property changes; trace
spending caps and uncertain outcomes; scoring claim/receipt recovery; lot worker,
reconciliation and destination handoff; valuation revision and historical replay.
No provider or model was invoked. Evidence: `feature-concurrency-result.json`;
raw local log: `logs/friday-feature-concurrency.log`.

This run uses minimal feature fixtures. It complements the populated saved-catalog
upgrade test; it does not prove live provider delivery, operator acceptance or
all new-feature interactions on the complete upgraded schema.

## October 22 pinned call, SMS contention and production drift

The separate `--postgres-sms` run passed eight-worker scheduler, work selection,
acknowledgment, generation, session binding, reply dispatch, recovery and carrier
reconciliation checks; each dispatch stage produced one claim. No providers were
called. Evidence: `transport-concurrency-result-2026-10-22.json`.

The full upgraded saved-catalog runner now invokes
`verify_versioned_call_concurrency.py`. It confirms eight actual independent
sessions wait on the same recipient advisory lock before competing. Both eight
versioned-call attempts and a mixed eight-attempt call/Twilio SMS race produce
exactly one claim and one persisted outbound record. The winning call retains
its agent, version and sender. Four attempted identity changes raise the immutable
identity exception and leave the saved row unchanged; reuse of the same reference
cannot claim again. These are local SQL claims with zero provider calls.

Fresh read-only production fingerprints captured October 22 at 10:40 Central
cover function definitions and ACLs in public/private/wholesale_ingest/offer_review.
Compared with the saved catalog: 120 existing functions, none missing, one expected
changed definition (`protect_retell_form_transport`), one expected new function
(`protect_facebook_submission`), and zero existing ACL changes. These are the
released Facebook migration's changes. Migration history still ends at
20261020192531. Checked offer-review, versioned-call and empty-session-recovery
entry points remain absent. Sources: `production-function-fingerprints-2026-10-22.json`
and `production-function-drift-2026-10-22.json`. This does not refresh table,
constraint, policy or trigger drift; full catalog comparison remains required.

Latest combined upgrade, pinned-call and intake run: ten journeys passed in 123.64 seconds. Raw log: `logs/friday-production-upgrade-pinned-calls.log`.

## October 22 full production shape refresh

`production_schema_shapes.sql` captures metadata only in a read-only transaction.
The saved-catalog/current comparison uses the same search path and non-pretty view
format, avoiding schema-qualification and parentheses artifacts. Actual deltas are
exactly the released Facebook table, job relationship/nullability, eleven constraints
and immutable trigger. Existing policies, standalone indexes, views and schema/default
grants are unchanged. Current application-schema sequences and enums are both zero.

`verify_production_schema_drift.py` compares the fresh snapshot with the disposable
catalog restored through the released Facebook migration. It matches 101 tables,
395 constraints, 113 standalone indexes, 28 triggers, 127 policies, 17 views, three
schema ACL sets and zero default ACL sets. Column order is retained. Only the local
fixture's owner roles are merged into postgres; production role names remain exact,
and privilege/grant-option rights are retained. An initial public-schema mismatch
was the disposable PostgreSQL pg_database_owner role, not production drift.

The original restore omitted view security/grants. It now restores the freshly
verified 17 `security_invoker=true` views and their ACLs, and the comparison checks
those settings too. With that correction, all eleven feature migrations, failure
rollback, pinned-call/SMS overlap and ten post-upgrade journeys pass (122.08 seconds).
No production business rows were copied.

`--schema-security` repeats restore, Facebook contention, current-shape comparison
and `verify_authorization.py`, then stops the disposable cluster. The authorization
check passes all five denied profile classes, forged user metadata, anonymous and
missing identity checks, while approved-admin changes succeed. Run:

```sh
.venv/bin/python scripts/run_offline_tests.py --schema-security
.venv/bin/python scripts/run_offline_tests.py --production-upgrade
```

Evidence: `production-schema-shapes-2026-10-22.json`,
`production-schema-drift-2026-10-22.json`, `production-upgrade-result.json`,
`authorization-verification-2026-10-22.json`,
`production-security-advisors-2026-10-22.json` and
`production-pause-observation-2026-10-22.json`. Raw local logs:
`logs/friday-production-upgrade-current-drift.log` and `logs/friday-schema-security.log`.
The advisory warnings remain recorded and were reviewed rather than suppressed.
