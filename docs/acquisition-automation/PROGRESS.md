# Acquisition automation — progress and resume checkpoint

Checkpoint date: October 25, 2026 (America/Chicago).
Status: live catalog inventory and additive design captured; implementation and activation not started.

## Latest checkpoint — live baseline and schema inventory

- Pulled planning branch before work; origin was up to date at `605f117`.
- Verified live Supabase project `dvzhzlipbwzzcliujzyz`; queried metadata only in READ ONLY transactions.
- Vercel hostname lookup returned production deployment `dpl_3VmD6PS8eWxGYPh5qzVCZ9ouWW5d`, READY, SHA `c8673c170368bc8c44974fd304fac5af3fcf6e8c`. Fetched this exact published commit for read-only inspection. Alias response omission and effective Vercel runtime flags/cron remain explicitly unverified.
- Captured 103 application tables, 17 views, 1,638 columns, 407 constraints, 248 indexes, 127 policies, 28 triggers, 122 function signatures/security settings and 95 live ledger entries. See `evidence/2026-10-25-catalog.json`; no business rows or secrets exported. This metadata snapshot is not a backup.
- Both private Retell schedulers are disabled and both Retell cron jobs inactive. Retention/monitor cron jobs remain active. No provider/worker was invoked.
- Confirmed a critical design gap: current application is shared approved-user access, with no workspace/tenant/organization ID columns in public/private/wholesale_ingest. Membership tenancy must be introduced and tested; existing development_workspaces is not an organization membership model.
- Confirmed existing county properties/contacts, campaign stores, native and website receipts, suppressions, analyses, recommendations, deals and buyers. Mapped all 16 PRD logical entities to extensions or justified additions in `SCHEMA-MAPPING.md`.
- Confirmed Facebook signature/receipt protections but synchronous inline processing; generic webhook_jobs lacks provider-event uniqueness. Added migration dependencies, compensation procedures and a disposable acceptance matrix in `MIGRATION-AND-TEST-PLAN.md`.
- Compared source/ledger: deployed source has 107 migration files; this planning base has 49, with 58 production files missing. Three live ledger names lack same-name production files. Comparison is not SQL-body equivalence. Do not release this older application tree or replay historical migrations.
- Validation performed: metadata/entity coverage and evidence consistency checks; `git diff --check`. Runtime, migration, RLS execution and live channel tests have not run.

Next: create an isolated implementation branch from refreshed deployed SHA, carry these documents forward, inspect affected function bodies/dependencies, and build the workspace membership foundation plus an inert disposable test harness. No unanswered question prevents that local work. Production migration and activation retain separate approval gates.

## Verified this session

- Original workspace was empty and not a Git repository.
- Located existing WholesaleOS checkouts and verified their origin: `https://github.com/julysses/Wholesale-automation.git`.
- Cloned origin into this workspace's `app/` directory and ran `git pull --ff-only`: already up to date.
- Clone default branch: `claude/ai-wholesaling-agency-KkDF1`.
- Planning base: `ad70c7c29d618efe3aad848a386ca1779f0e7b8f` — Handle transient availability failures and preserve current production release.
- Created documentation branch: `codex/acquisition-prd-v1-plan`.
- No repository AGENTS.md was found by file inventory. User-supplied instructions govern: Codex pulls/pushes updates; GPT Work maintains a resumable planning/progress file.
- Captured all PRD requirement groups, logical entities, ordered activation gates and acceptance expectations in `IMPLEMENTATION-PLAN.md`.

## Checklist

- [x] Locate source repository and pull current default branch.
- [x] Save implementation plan and durable progress record.
- [ ] Verify deployed production code/schema and paused operations against current evidence.
- [x] Identify deployed revision, read live catalog and database scheduler state; effective platform/provider controls still pending.
- [x] Inventory existing schema, migration history, RLS, roles and equivalent entities.
- [x] Complete `SCHEMA-MAPPING.md` before writing SQL.
- [x] Document forward-only migration sequence, compensation and planned disposable tests.
- [ ] Build/test shared foundation on a disposable database.
- [ ] Implement and pass Facebook acceptance with approved test leads.
- [ ] Obtain any required production migration/activation approvals.
- [ ] Pass inbound calling/mail gate.
- [ ] Pass portal/proposed-batch gate.
- [ ] Pass human-caller gate.
- [ ] Pass agency controlled-pilot gate.

## Repository context — not production verification

Earlier local checkouts have different heads:

- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app`: `codex/facebook-release-candidate`, `8e08409`, clean at inspection.
- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/integration`: `codex/wholesale-integration-review`, `c63f7d5`, two untracked duplicate-named schema files. Left untouched.
- `/Users/juliodominguez/Documents/Codex/2026-10-20/a-review-of-the-wholesaleos-github/facebook-release`: `codex/facebook-release-candidate`, `4480112`, clean at inspection.

Their relationship to the deployed baseline has not been verified. Do not reconstruct or merge an unpublished candidate from these references. Historical memory suggested prior paused Facebook work; current provider, schedule and deployment state was not queried.

## Exact resume steps

1. Enter `/Users/juliodominguez/Documents/Codex/2026-10-25/wholesaleos-acquisition-automation-prd-version-1/app`.
2. Check branch/status; pull its upstream with `git pull --ff-only` before changes. Preserve unrelated work.
3. Read this file, `IMPLEMENTATION-PLAN.md`, `SCHEMA-MAPPING.md` and `MIGRATION-AND-TEST-PLAN.md`. Refresh the deployed revision before creating the implementation branch; this planning branch contains older application code.
4. Load the Supabase skill and inspect affected function bodies/dependencies beyond the captured signatures; verify platform/provider controls without retrieving unrelated secrets. Read current official provider docs when implementing APIs.
5. Build the isolated workspace-membership implementation and disposable harness from the verified production revision. Use the captured mapping/conflict list to extend equivalents; do not replay historical migrations or touch held SMS work.
6. Update this checkpoint with concrete evidence, changes, remaining blockers and next action; commit and push each completed update.

## Validation and external effects

Documentation-only change: verify requirement coverage and `git diff --check`; runtime tests are not applicable. No SQL, app code, provider configuration, scheduling, advertising, outreach, mail, offer transmission or contract execution changed. No production rollout is claimed. Git commit/push completion is reported separately after verification; inspect branch upstream and latest log when resuming.
