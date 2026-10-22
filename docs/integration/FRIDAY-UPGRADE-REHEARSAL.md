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
- All ten post-upgrade journeys passed (122.25 seconds): Hilltop, Jays and native Facebook acknowledgment/reply/receipts/STOP/no-replay, missing consent, missing-owner recovery and lost native receipt-response retry.

Machine-readable evidence: `production-upgrade-result.json`. Raw log: `logs/friday-production-upgrade.log` (local ignored file). Migration hashes are recorded in the result.

## Limits and next work

This uses the saved October 20 catalog plus the separately released Facebook migration, not a fresh complete production export. It uses synthetic history and stubbed Auth/network/cron facilities. Land/valuation and versioned-call historical tables need populated compatibility fixtures; feature-specific native offer/lot/valuation/call-identity concurrency and R1–R12 acceptance remain open. A successful rollback of the whole sequence does not yet prove injected mid-sequence failure handling or production-volume lock behavior.

Next: strengthen those fixtures and failure-path checks, run feature concurrency under isolated ingress, compare relevant catalog drift, and review the exact schema/runtime release boundary. Do not deploy this branch, apply these migrations, activate collection or messaging, or replay held work on the basis of this evidence. Full Friday launch remains dependent on live controlled delivery and operator acceptance as well as the chosen integrated feature set.
