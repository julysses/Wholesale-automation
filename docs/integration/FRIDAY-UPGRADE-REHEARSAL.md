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

This uses the saved October 20 catalog plus the separately released Facebook migration, not a fresh complete production export. It uses synthetic history and stubbed Auth/network/cron facilities. Populated compatibility fixtures now cover land, valuation and four historical call statuses; Real PostgreSQL offer/lot/valuation, trace-budget, scoring and restricted-ingress concurrency now pass using separate minimal fixtures. Full pinned-call overlap and requirement-by-requirement R1–R12 acceptance remain open. An injected SQL failure after migration six now proves rollback of partial DDL, functions and retained rows. Production-volume lock behavior remains unproven.

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
