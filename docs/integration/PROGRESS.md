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
- [ ] Reconcile schema manifest; no live schema inspected yet.
- [ ] Port human-offer/draft safeguards with matching API/UI contracts.
- [ ] Port lot/valuation bundles without historical migration replay.
- [ ] Port versioned-call identity with matching API/schema/ACL transition.
- [ ] Validate production intake/consent/suppression/receipt invariants locally after authorization.
- [ ] Prepare draft PR and paused release plan.

## Deployment and test containment

Only the new integration ref may be pushed. Never push the production/default/collection refs. The new ref is explicitly disabled in `vercel.json`. Existing availability monitoring runs on the default branch; do not dispatch it. Existing Railway checkpoint records default-branch deployments; read-only Railway configuration checks on October 20 confirmed all three linked services still source `claude/ai-wholesaling-agency-KkDF1`, not this integration branch. Existing staged changes were left untouched. No deploy CLI or provider worker is part of this work.

## Next checkpoint

Review and port the human-offer bundle first. Preserve production imports, linked inquiry navigation, notifications, SMS transport and all receipt handlers. Record exact changed files and checks for each bundle here. New SQL must remain an unapplied proposal until actual production schema/history is reconciled.
