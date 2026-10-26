# Acquisition automation — progress and resume checkpoint

Checkpoint date: October 25, 2026 (America/Chicago).
Status: implementation in progress on `codex/acquisition-foundation`; production remains unchanged.

## Implementation checkpoint — acquisition account and lead boundaries

- Pulled `codex/acquisition-foundation` at `0442725`; worktree was clean. Previous goal turn is classified as progress (committed/pushed foundation and verified tests), not a wait or blocker.
- Added CLI-generated migration `20261026025259_acquisition_legacy_access_boundary.sql`: sticky acquisition-only profile flag; restrictive shared-table policies; a workspace-to-canonical-lead/property binding; audited binding/assignment functions; bounded assigned-lead projection. No duplicate lead/property data or automatic ownership backfill.
- Non-owner membership enrollment sets acquisition_only; revocation never restores shared legacy access. Existing non-owner memberships are covered when upgrading. Platform admin identities cannot be enrolled as limited caller/agency accounts. Existing account approval remains required.
- Legacy API authentication reads the optional new profile field compatibly with the prior schema and denies acquisition-only identities outside acquisition routes/the explicit eligibility endpoint. Internal routes now also require authentication. Raw scoped-lead mutation is denied to authenticated clients; mutations go through reviewed RPCs.
- Binding requires both a legacy platform administrator and workspace owner. County property association must already match the selected canonical lead. One lead/property cannot be adopted into two workspaces. Assignment requires a current member of the same workspace. Caller/agency queue projection requires MFA and explicit lead assignment, exposes no contact numbers, and caps pages at 50.
- Validation: **22 disposable PostgreSQL tests pass**, including preserved canonical property/lead data, same-phone nonmerging, preexisting membership upgrade, cross-workspace/raw-write denial, sticky revocation and assigned caller access. **121 targeted backend tests pass**, with 24 preexisting datetime warnings. `git diff --check` passes. Same isolated commands/runtime as the prior checkpoint; no provider connections or production writes.

**Remaining security gate:** acquisition-only identities are contained, but existing legacy service-role handlers can still bypass RLS when used by a legacy account. They must be scoped/bridged or denied access to newly bound resources before production binding/activation. Related child records (contracts, offers, etc.) still need workspace ownership propagation. This slice does not claim complete multi-tenant isolation. No production account was enrolled or lead bound.

Next: finish legacy service-path isolation, then add canonical contact/evidence links, immutable per-channel permission and eligibility decisions, and durable Facebook receipts/processing. Full production-shaped upgrade rehearsal and later phase implementation remain open. Goal stays active.

## Implementation checkpoint — workspace foundation

- Refreshed Vercel production identity: still `c8673c170368bc8c44974fd304fac5af3fcf6e8c` / `dpl_3VmD6PS8eWxGYPh5qzVCZ9ouWW5d`.
- Created `codex/acquisition-foundation` from that exact deployed commit, preserving the complete production tree. Carried only the acquisition planning documents from `3fe1e9b`; no older application tree merged.
- Added `20261026024157_acquisition_workspace_foundation.sql` with the Supabase CLI. Additive workspaces/memberships, approved-profile and live-session checks, caller/agency MFA, owner/admin administration, last-owner protection, RLS and scoped immutable events in existing audit_logs. No legacy records auto-assigned.
- Added disabled-by-default `/api/acquisition/workspaces` and membership endpoints. User JWT and public Supabase key are forwarded to PostgREST; no service-role fallback. RPC authorization lives in private schema; public wrappers are security invoker. Input validation rejects supplied actor identity.
- Added a disposable Unix-socket-only PostgreSQL runner (no TCP, inherited secrets, cron/net extensions or provider SDKs). Reconstructs exact inspected column/constraint shapes for touched legacy profiles/audit dependencies, uses synthetic users/sessions and preserves legacy audit sentinels. It is a focused upgrade test, not a complete 103-table production restore.
- Added CI execution of the PostgreSQL foundation suite and disabled automatic Vercel deployments for this implementation branch.
- Validation: **15 real PostgreSQL tests pass**, including parallel creation and concurrent owner removal; **111 targeted backend tests pass** (14 acquisition HTTP cases plus existing auth/Facebook/Retell protections). Existing tests report 24 datetime deprecation warnings. `git diff --check` passes.
- Test commands: `python3 scripts/test_acquisition_workspace.py`; existing offline runner with the previously installed Python runtime at `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app/.venv/bin/python` against `tests/test_acquisition_api.py`, `test_api_auth.py`, `test_facebook_consent.py`, `test_facebook_request_security.py`, `test_facebook_sms_handoff.py`, `test_facebook_receipt_race.py`, `test_retell_webhook_security.py`. External runtime was used read-only; no old checkout changed.
- Sandbox shared-memory restriction required approval for the disposable PostgreSQL runner; it completed and destroyed its own test cluster.

**Not complete at this earlier checkpoint:** existing CRM/county tables and old service-role endpoints still use legacy shared access. The newer checkpoint above adds caller containment/bindings but retains the service-role bridge gate. Do not enable acquisition until all boundaries and full upgrade acceptance pass. No production migration, feature flag, provider configuration or schedule changed.

Next implementation slice: add workspace-bound lead/property/contact relationships and server-side authorization for legacy-resource bridges; preserve county property IDs and existing receipts. Then implement immutable channel permission/eligibility records and durable Facebook inbox. Keep the goal active through remaining PRD slices and acceptance gates.

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

This inventory checkpoint is historical; the implementation checkpoint above supersedes its next action. Production migration and activation retain separate approval gates.

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
- [x] Start isolated implementation branch from deployed production revision.
- [x] Implement/test workspace membership, administration API and scoped audit foundation.
- [x] Implement/test acquisition-only legacy-access containment, canonical lead/property binding and assigned-lead projection.
- [ ] Scope legacy service-role handlers and propagate workspace ownership to related records.
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
3. Read this file, `IMPLEMENTATION-PLAN.md`, `SCHEMA-MAPPING.md` and `MIGRATION-AND-TEST-PLAN.md`. Continue `codex/acquisition-foundation` (production-based); do not switch back to the older planning branch for code work.
4. Load the Supabase skill and inspect affected function bodies/dependencies beyond the captured signatures; verify platform/provider controls without retrieving unrelated secrets. Read current official provider docs when implementing APIs.
5. Continue the shared foundation with workspace-bound legacy identities, authorization bridges, contact permissions/eligibility and durable ingestion. Use the captured mapping/conflict list to extend equivalents; do not replay historical migrations or touch held SMS work.
6. Update this checkpoint with concrete evidence, changes, remaining blockers and next action; commit and push each completed update.

## Validation and external effects

Implementation is local and tested as recorded above; migration files are proposals for later approval. No production database, provider configuration, scheduling, advertising, outreach, mail, offer transmission or contract execution changed. No production rollout is claimed. Git commit/push completion is reported separately after verification; inspect branch upstream and latest log when resuming.
