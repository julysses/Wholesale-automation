# Selective WholesaleOS integration

## Authorization and operating boundary

October 20, 2026: owner said “Proceed with your recommendation” after the branch integration assessment. Local implementation is resumed on `codex/wholesale-integration-review`, based on production `19c117ad7a8ab10656bf116a2a6835508f7f1f01`. Collection source is `8bec6d825071993d59bc623b346046c3f249fba2`.

Production deployments, database migrations, SMS repair/dispatch, provider activity, collection and schedules remain paused. Local isolated test authorization was requested separately because the prior brief prohibited new tests. Until answered, no tests or CI runs are authorized; use `[skip ci]` for checkpoint commits.

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
- [ ] Validate production intake/consent/suppression/receipt invariants locally after authorization.
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
- Byte comparison confirmed 19 protected production intake/SMS/receipt/notification modules and all 103 preexisting migration files remain unchanged.
- Read-only production metadata confirmed missing feature objects and the non-deleting monitoring function; no data or control-state changes.
- These are static checks only. Build, typecheck, local SQL execution, backend/frontend tests and end-to-end acceptance remain unrun.

## Next checkpoint

The initial plan/deployment-isolation checkpoint is `bc8052e`. Prepared feature commit `f675e26c1690223c0d2d8dc909b97282e9e2ab70` is pushed. Draft PR [#21](https://github.com/julysses/Wholesale-automation/pull/21) targets `codex/retell-sms-production`; it is not ready to merge or deploy. GitHub read-back confirmed the expected head/base, zero Actions runs for the integration branch, and no GitHub deployment records for it at the checkpoint. Those API observations do not substitute for a full live release audit. Subsequent checkpoint commits continue to use `[skip ci]` while test permission is pending.

After explicit local-test authorization, install dependencies in this isolated checkout and run the relevant suites with production secrets absent and providers blocked/mocked. Resolve failures, add missing cross-feature regression coverage, and satisfy the assessment's R1–R12 before requesting release approval. The full production-shaped schema-upgrade rehearsal is still outstanding.
