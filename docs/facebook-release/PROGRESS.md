> **Latest state — released October 20, 2026:** PR #22 is merged and serving production at `a89815126d9a98ced016167d8e383641d133135f`. Only the Facebook migration was applied. Messaging and outbound schedules remain paused. See [the release checkpoint](RELEASED-PAUSED.md) for verification scope and remaining live-test approval. The preparation record below is historical.

# Facebook-only release candidate — October 20, 2026

Goal: reach a production-ready application as quickly as verified evidence permits. This checkpoint prepares the Facebook release for owner review; it does not authorize production activation.

## Scope and current boundary

- Candidate branch: `codex/facebook-release-candidate`.
- Base: `codex/retell-sms-production` at `19c117ad7a8ab10656bf116a2a6835508f7f1f01` (refreshed October 20).
- Facebook repair originally reviewed in integration commit `27d233b`, extracted as a patch rather than copying the integration versions of shared files.
- County collection, valuation, offer, and call changes from PR #21 are excluded.
- Four runtime files change: `tools/facebook_inquiry.py`, `tools/retell_form_sms.py`, `tools/sms_client.py`, `web/api/webhooks.py`.
- Exactly one forward migration: `20261020184154_facebook_inquiry_sms_receipts.sql`.
- All 103 historical migration files are unchanged. The older empty-session reconciliation file remains in the inherited repository but is explicitly **not part of this release** and was not applied in the rehearsal.
- `vercel.json` disables deployments from this candidate branch. Commits use `[skip ci]`. No production/default/collection branch is updated.
- Production writes, live messages, provider calls, collection schedules and SMS schedules remain paused.

## Completed

- [x] Isolate the Facebook repair on the current production branch.
- [x] Capture application catalog definitions with `BEGIN READ ONLY`; copy no customer rows, credentials, auth sessions, or vault values.
- [x] Restore 100 tables, 120 functions, 384 constraints, 113 standalone indexes, 27 triggers, 127 policies and 17 views in disposable PostgreSQL 17.
- [x] Preserve actual generated columns, application table/function privileges, RLS policies, and deployed function bodies.
- [x] Seed synthetic website work across both transports and all five existing statuses; seed held sessions/turns, provider receipts and suppressed leads.
- [x] Rehearse the single migration inside a transaction, roll it back, verify restoration, then apply it locally and verify unchanged historical rows across all 100 original tables.
- [x] Confirm all 91 deployed migration-history entries stay unchanged; no historical migration replay.
- [x] Confirm only the intended existing transport-protection function changes; its ACL stays unchanged.
- [x] Exercise eight concurrent native requests, immutability, source identity constraints, browser-role denial and service-role insertion.
- [x] Fix a genuine competing-insert edge case: PostgreSQL can report another unique index before the primary-key conflict arbiter. Recover only SQLSTATE `23505` through exact-ID readback; immutable evidence must still match. Other failures remain errors.
- [x] Run ten complete local HTTP/SQL journeys using mocked provider boundaries, including the real 60-second website acknowledgment delay.
- [x] Python regression suite: 1,131 passed; ten disposable-database tests skipped in the generic run and executed separately.
- [x] Pipeline/SQL suite: 196 passed.
- [x] Frontend suite: 179 passed in 42 files, bounded to two workers.
- [x] TypeScript and Vite production build passed; existing bundle-size warning remains.
- [x] Final application-service-role journey run: all ten passed; evidence packaged in `validation.json` and `evidence/`.
- [x] Pushed candidate and opened [draft PR #22](https://github.com/julysses/Wholesale-automation/pull/22) targeting `codex/retell-sms-production`.
- [x] Verified no GitHub Actions runs or GitHub deployments for this candidate branch. Read-only Railway configuration confirms all three existing services track the old default branch, not this candidate.

## Production-shaped rehearsal limits

Source: `production-catalog.json`, captured 2026-10-20 at 18:59:58 UTC from the production catalog; `production-metadata.json` records deployed history, schema privileges and disabled schedulers. These are structural observations, not an export of business records.

The local cluster restores application SQL in `public`, `private`, and `wholesale_ingest`. Supabase-managed Auth is represented by a minimal synthetic user table and JWT claim functions. Object ownership maps to the disposable database administrator. UUID and crypto extensions run locally. Vault is empty; network functions raise errors; cron is an inert table with inactive entries. Supabase Auth/PostgREST/Realtime services and actual provider infrastructure are not exercised. Application database calls use a small PostgREST-shaped SQL adapter; final journey coverage uses `service_role` permissions.

This rehearsal proves schema and application compatibility with synthetic history. It does not establish production-volume lock duration, Meta subscription/permission health, live email delivery, carrier/handset delivery, or operator acceptance. No application schema was weakened to make a test pass. Early loader failures required generated-column support, correct parameter handling for SQL bodies, empty-ACL handling, and valid synthetic owner/configuration records.

## Exact eventual release sequence — requires owner review first

1. Review this candidate and evidence. Reconfirm the intended deployed application revision, live Meta form/page mapping, selected intake owner and website form configuration without modifying them. Other remote branches have advanced; they are not automatically included.
2. Keep both SMS schedulers and both Retell cron jobs disabled. Keep collection schedules paused. Preserve held and previously attempted work; no bulk repair or replay.
3. Recheck the relevant production catalog and migration history for drift. Review a backup/recovery point and production lock budget. Apply **only** the named Facebook migration in one transaction with bounded lock/statement timeouts; stop rather than widening scope if preconditions differ. Do not run a directory-wide migration push or history repair.
4. Verify the native table, exact-source constraint, identity foreign key, immutable trigger, RLS and grants. Compare existing website jobs, receipts and suppression before/after.
5. Deploy only the approved Facebook runtime delta with live messaging and schedules still disabled. Keep the native migration in place if application rollback is needed; do not drop receipt evidence or repurpose native jobs as website jobs. Prefer a forward fix after any native data has arrived.
6. With separate explicit authorization, perform fresh controlled Facebook Instant Form and website submissions. Verify one CRM lead, approved owner, due task, visible operator alert and owner notification. Validate actual Meta authorization/subscription and the real website endpoints.
7. With separate explicit authorization for live provider acceptance, use fresh test inquiries only. Prove acknowledgment, signed delivery callback, handset receipt, seller reply, operator task, Retell generation, reply delivery, STOP/DNC suppression and no replay. Provider acceptance alone is insufficient. START alone must not clear DNC.
8. Review results before any scheduler activation or ad spend. Never release the county integration as part of the Facebook launch. Until live checks pass, status remains **candidate ready for review**, not full go-live certification.

## Reproduction and next checkpoint

From this candidate directory, with Python requirements and the pinned Node lockfile dependencies installed:

```sh
.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests
.venv/bin/python scripts/run_offline_tests.py npm --prefix pipeline test
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test -- --maxWorkers=2
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend run build
.venv/bin/python scripts/run_offline_tests.py --lead-journeys
```

The last command creates a new loopback-only `wholesale_sms_test` cluster, restores the catalog, rehearses only the Facebook migration, runs the connected tests and stops/removes the cluster in `finally`. It accepts no production connection string. The external-network guard and clean environment prevent inherited provider credentials from being used. Local environment dependencies were reused only after comparing candidate and integration lockfiles; no dependency update is part of this candidate.

## Saved handoff

Implementation and test-evidence commit: `bd3f0c2d5951e99cba584c30fdc171d309312e93`. This documentation follow-up records the verified PR and publication state; runtime code and validated migration are unchanged.

Next action requires owner review of PR #22 and explicit production-release authorization. Local candidate preparation is complete. Overall production readiness remains open until the deployment and controlled live acceptance gates above pass. Do not infer authorization from this checkpoint or from the overall goal.
