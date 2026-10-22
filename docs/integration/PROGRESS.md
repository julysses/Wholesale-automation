# Selective WholesaleOS integration

## October 21 Friday launch continuation

See `FRIDAY-UPGRADE-REHEARSAL.md`: saved production-shaped catalog restoration, the released Facebook migration, the eleven integration migrations, rollback/preservation/permissions and all ten post-upgrade intake journeys now pass locally. This supersedes the missing full-catalog composition evidence below, but not feature concurrency, fresh catalog drift, live acceptance or release authorization. Active checkout is in the October 21 launch workspace's `integration/` directory.

## Current checkpoint: native Facebook handoff repaired locally

Owner explicitly authorized the handoff fix and connected local journeys. See `FACEBOOK-HANDOFF-FIX.md` and `facebook-handoff-release-manifest.json`. Ten connected API/PostgreSQL cases, an eight-worker native race, 1,261 backend tests, 231 pipeline tests and 240 frontend tests passed. The native `no_form_receipt` blocker is fixed locally; no production release or live acceptance is claimed.

- [x] Persist immutable native receipts and queue them without fake website submissions.
- [x] Verify both websites and native Facebook through acknowledgment, reply, receipts and STOP using mocked providers.
- [x] Verify missing-owner/lost-response recovery, no consent, and no replay.
- [ ] Review proposed native migration/runtime and sanitized production-shaped upgrade.
- [ ] Separately authorize any production release and bounded live acceptance.

## Authorization and operating boundary

October 20, 2026: owner said “Proceed with your recommendation” after the branch integration assessment. Local implementation is resumed on `codex/wholesale-integration-review`, based on production `19c117ad7a8ab10656bf116a2a6835508f7f1f01`. Collection source is `8bec6d825071993d59bc623b346046c3f249fba2`.

Production deployments, production database migrations, live SMS dispatch, provider activity, collection and schedules remain paused. Local handoff repair is authorized. The owner explicitly authorized local testing with mocked providers and disposable databases on October 20, prioritizing BOTH Facebook Instant Forms and website forms. Remote CI is not part of that authorization; continue `[skip ci]` checkpoint commits. Production and provider operations remain paused.

The empty-session reconciliation migration remains outside this work and unapplied according to the production checkpoint. No held message may be replayed.

## Progress

- [x] Created an isolated clone without local environment files.
- [x] Pulled production with `--ff-only`; already current at the pinned SHA.
- [x] Created integration branch; original production checkout untouched.
- [x] Added exact integration-branch Vercel deployment exclusion.
- [x] Removed tracked machine-specific `pipeline/node_modules` symlink from this checkout.
- [x] Read-only production migration/catalog snapshot captured in `schema-manifest.json`; full upgrade acceptance remains pending.
- [x] Prepared human-offer/draft safeguards with matching API/UI contracts.
- [x] Prepared lot/valuation bundles with eleven newly generated forward migration files across all features; no historical migration was imported or applied.
- [x] Prepared versioned-call identity with matching API/schema/ACL transition.
- [x] Executed local intake/consent/suppression/receipt regressions; native Facebook Retell handoff blocker found (not launch acceptance).
- [x] Opened draft PR #21 against production and documented the paused release boundary.

## Deployment and test containment

Only the new integration ref may be pushed. Never push the production/default/collection refs. The new ref is explicitly disabled in `vercel.json`. Existing availability monitoring runs on the default branch; do not dispatch it. Existing Railway checkpoint records default-branch deployments; read-only Railway configuration checks on October 20 confirmed all three linked services still source `claude/ai-wholesaling-agency-KkDF1`, not this integration branch. Existing staged changes were left untouched. No deploy CLI or provider worker is part of this work.

## Prepared implementation

- Source ports: `ported-source-files.json` lists 97 collection-only code/fixture/test files. Shared API/UI files were reconciled separately.
- Production `web/api/__init__.py` keeps import reconciliation and adds only the offer/outreach contract changes.
- Production `Leads.tsx` retains server CSV imports and inquiry deep links; contract-price autofill is removed, and explicit follow-up-date validation is restored.
- Production Daily Lists keeps inline property verification, tax warnings and PropStream controls; lot controls load only when opened.
- Production `ingress-postgres.ts` keeps the restricted collector role and notice-history assertions; collection offer/lot/valuation contention suites are added.
- `forward-migration-map.json` records source-to-new filenames. `forward-migration-order.json` is the explicit proposed execution order; all eleven files remain unapplied.
- The four old collection SMS-install migrations were excluded. The empty-session repair was neither altered nor applied.
- `RELEASE-BOUNDARY.md` documents the schema/runtime transition and why a blanket migration push is prohibited.

## Verification actually performed

- Parsed 34 changed/new Python files as syntax trees; no application imports, test execution, provider calls or database writes.
- `git diff --check` found no whitespace errors.
- At the initial preparation checkpoint, byte comparison confirmed 19 protected modules and all 103 historical migrations unchanged. The authorized Facebook repair now intentionally changes `tools/retell_form_sms.py` and `tools/sms_client.py`; the other 17 protected modules and all historical migrations remain unchanged.
- Read-only production metadata confirmed missing feature objects and the non-deleting monitoring function; no data or control-state changes.
- Those initial checks were static. October 20 local execution is recorded in `FACEBOOK-LAUNCH-READINESS.md`; full end-to-end and production-shaped upgrade acceptance remain outstanding.

## Next checkpoint

The initial plan/deployment-isolation checkpoint is `bc8052e`. Prepared feature commit `f675e26c1690223c0d2d8dc909b97282e9e2ab70` is pushed. Draft PR [#21](https://github.com/julysses/Wholesale-automation/pull/21) targets `codex/retell-sms-production`; it is not ready to merge or deploy. GitHub read-back confirmed the expected head/base, zero Actions runs for the integration branch, and no GitHub deployment records for it at the checkpoint. Those API observations do not substitute for a full live release audit. Subsequent checkpoint commits continue to use `[skip ci]` while remote CI remains outside the local testing scope.

Local-test authorization is now granted. Install dependencies in this isolated checkout and run the relevant suites with production secrets absent and providers blocked/mocked. Resolve failures, add missing cross-feature regression coverage, and satisfy the assessment's R1–R12 before requesting release approval. The full production-shaped schema-upgrade rehearsal is still outstanding.

## Resumed local acceptance work

- [x] Owner selected both ad destinations.
- [x] Added clean-environment, no-network Python/Node runner.
- [x] Executed backend, UI, disposable PGlite and real PostgreSQL SMS contention suites. Corrected obsolete UI test cache-key expectation.
- [x] Recorded results and remaining gates in `FACEBOOK-LAUNCH-READINESS.md`.
- [x] Repaired native Facebook receipt/Retell queue relationship after owner authorization; connected API/database journey acceptance passes for both destinations.
- [ ] Complete production-shaped eleven-migration upgrade and remaining feature concurrency rehearsals.

Latest local evidence: 1,256 backend tests passed; native Facebook rerun 25 passed including two added hold reproductions; 230 pipeline tests passed; initial UI 239/240 with stale assertion corrected and its three-test file passing. Build passed, no new lint findings (144 existing). Eight-worker disposable PostgreSQL contention passed with zero provider calls. No production changes, messages or schedules. This is not a launch certification.
