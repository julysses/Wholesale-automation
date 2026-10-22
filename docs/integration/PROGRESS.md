# Selective WholesaleOS integration

## Latest October 22 checkpoint — locked Python dependencies and audit

- [x] Hash-pin all 84 root and 61 API dependencies at the already-tested versions;
  preserve source declarations and isolate 29 hash-pinned CI audit-tool packages.
- [x] Audit all three complete sets: zero known vulnerabilities, no skipped/ignored
  packages. The old local pip inventory finding is separated from app packages.
- [x] Make supported Python 3.12 explicit for Vercel; align CI/Docker/legacy runtime
  metadata and CI/Docker pip 26.2.2. No production runtime was changed.
- [x] Clean root/API/tool installs and pip check; fresh root 1,345/10 skipped;
  API-only real cold start, health, buyer access rejection and Twilio version pass.
- [x] Hash-verified Linux x86 wheel download for all 84 root packages; YAML and lock
  checks pass. Add CI checks for locked dependency audits and API-only cold start.
- [ ] Linux/Docker/Vercel artifact execution, production interpreter/installer,
  JWT/tenancy/security review and all remaining operator/live/release gates.

See `PYTHON-DEPENDENCY-SECURITY.md` and its current audit JSON. Fourteen unapplied
migration proposals, candidate deployment exclusions and broad schedule pause
remain unchanged. Existing frontend 295/pipeline 231 evidence was not re-run for
unchanged sources; no production writes, provider calls or remote CI execution.

## Latest October 22 checkpoint — atomic buyer CSV recovery

- [x] Replace background partial buyer persistence and insert fallbacks with one
  server-only data/log/immutable-receipt transaction and stable explicit retries.
- [x] Preserve existing buyer controls and consent; never infer opt-in from contact
  presence or bind imported contacts to a blank already-consented destination.
- [x] Refuse conflicting identities/history, invalid prices and ambiguous same-name
  buyers. Missing finance data is not cash; duplicate rows do not inflate signals.
- [x] Prove real SQL commit/lost-response recovery, full rollback, all 1,003 purchase
  rows and four competing import sessions. Above-limit source rows are refused.
- [x] Backend 1,345/10 skipped; frontend 295/59 files; pipeline 231; build/typecheck
  and lint gate pass (142 existing findings). No provider/model calls.
- [ ] Production-volume locks, APN event-history review, signed-in browser/reload
  recovery, manual-create ambiguity, durable explicit classification/rescoring,
  outreach-log completeness and remaining live/security/release gates.

The allowlist now has fourteen unapplied proposals. See `BUYER-CSV-TRANSACTION.md`.
PR #21 remains draft; production and broad schedules remain unchanged.

## Latest October 22 checkpoint — buyer reads and preferences

- [x] Complete count-checked buyers, leaderboard and land-buyer reads; 25-record
  pages, literal search, uncategorized land visibility and explicit error recovery.
- [x] Buyer-specific purchase history with cancellation, response identity/count
  checks, bounded rendering and no false empty result after failure.
- [x] Complete active-buyer matching and classifier history; expose existing
  active/land/infill/category preferences while preserving nullable values.
- [x] Local SQL proves 1,003 buyers/history rows with a forced 200-row cap; a best
  match beyond row 1,000 wins and deactivation excludes it. Zero provider calls.
- [x] Backend 1,340/10 skipped; frontend 289/58 files; build/typecheck and lint gate
  pass (143 existing findings). Pipeline source retains prior 231-test evidence.
- [ ] Finish buyer import/acknowledgment and background-result review, outreach-log
  completeness, signed-in operator acceptance and all remaining live release gates.

See `BUYER-READ-COMPLETENESS.md`. No new migration or production mutation. Thirteen
proposed migrations remain unapplied; broad schedules stay paused and PR #21 draft.

## Latest October 22 checkpoint — durable AI batch recovery

- [x] Read current Vercel runtime metadata: Python/FastAPI, Fluid enabled; no settings
  changed and effective per-function duration remains unverified.
- [x] Replace the one-request/all-model-calls checkpoint with private batches <=25,
  immutable terminal evidence and one submitted batch per import.
- [x] Original upload replay cannot advance later paid batches; read-only progress
  and explicit continuation preserve exact replay semantics.
- [x] Add operator recovery panel with single/all remaining scoring, pause after
  current batch, last-confirmed totals and no automatic retry after uncertainty.
- [x] Verify 60-row completion, partial unknown/lost-result recovery, immutable
  evidence, foreign-actor denial and actual eight-session batch contention.
- [x] Refuse oversized bodies before submission; preserve all 10,000 short rows
  in the complete transport test. No silent truncation or partial auto-split.
- [ ] Complete real-provider/maximum-volume latency, buyer UI, signed-in operator
  acceptance, Python security review, exact release/recovery and live delivery gates.

See `CSV-BATCH-RECOVERY.md`. No production mutation or provider calls; PR remains
draft and Friday's full launch objective remains active.


## Latest October 22 checkpoint — connected CSV intake

- [x] Connect verified Auth/API to atomic data receipts with no unsafe fallback.
- [x] Add one-way optional AI claim/finish, strict IDs/scores, SDK retry disable,
  exact replay and stale-work preservation.
- [x] Verify actual commit-then-lost-ack recovery at data, claim and result boundaries;
  eight contending claims yield one dispatch authority; unknown attempts never repeat.
- [x] Connect Leads, standalone modal and Master List with correlated results and
  stable request IDs; Master List preserves identity across SPA remounts and uses
  atomic free rules scoring instead of starting a global background run.
- [x] Correct numeric cleaning so negative/malformed values cannot become positive.
- [x] Backend 1,325 pass/10 skip; frontend 262/54 files; build/typecheck/lint gate pass.
- [x] Thirteen-migration upgrade/rollback/history and ten intake journeys pass;
  real Auth/model boundaries remain stubbed and provider calls remain zero.
- [ ] Review large optional AI upload execution time and partial-batch recovery.
- [ ] Finish buyer UI, signed-in operator review, security and exact release/recovery.
- [ ] Complete fresh live destination/Meta/provider acceptance, then owner review.

No production changes; PR #21 stays draft and broad sending schedules stay paused.
See `CSV-LEAD-TRANSACTION.md`, manifest/results and `FRIDAY-ACCEPTANCE-STATUS.md`.


## Earlier October 22 main CSV database foundation

The original application importer still needs replacement. The thirteenth proposed
migration now provides an atomic data transaction, immutable same-reference replay,
approved configured intake ownership, linked due tasks, safe blank-field merging
and free rules scoring without rewriting worked/DNC records. Eight overlapping
manual uploads create one property/task. A 501-row import creates 501 owned tasks.
AI intent is durable only; provider claim/finish and API/UI integration remain open.
See `CSV-LEAD-TRANSACTION.md` for exact tests and next implementation. No production
changes or provider calls; PR #21 remains draft and schedules stay paused.

- [x] Prepare real-SQL transaction foundation with server-only receipt access.
- [x] Verify configured owner, due task, exact retry, ambiguity refusal and overlap.
- [x] Preserve worked fields, completed tasks, long provenance and no-change rows.
- [ ] Add durable AI claims/results and uncertain-attempt handling.
- [ ] Connect verified Auth/API receipts and stable per-upload browser retries.
- [ ] Complete application/SQL and operator acceptance, then exact release review.

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
- [x] Complete populated saved-catalog eleven-migration upgrade, injected failure rollback and ten post-upgrade intake journeys.
- [x] Execute separate real PostgreSQL offer/lot/valuation/trace/scoring/ingress concurrency.
- [ ] Complete remaining R1–R12 acceptance, pinned-call overlap, fresh catalog drift, live delivery and operator walkthrough.

Latest local evidence: 1,256 backend tests passed; native Facebook rerun 25 passed including two added hold reproductions; 230 pipeline tests passed; initial UI 239/240 with stale assertion corrected and its three-test file passing. Build passed, no new lint findings (144 existing). Eight-worker disposable PostgreSQL contention passed with zero provider calls. No production changes, messages or schedules. This is not a launch certification.

## October 22 current verification

Current backend: 1,269 passed, 10 skipped. Current frontend: 240 passed across 51
files. Pipeline: 231 passed. Build and lint gate pass (144 existing findings).
Full populated upgrade and ten journeys pass; nine real PostgreSQL concurrency
groups pass. Frontend dependency audit is clear after compatible patches.
Continue from `FRIDAY-UPGRADE-REHEARSAL.md` and `FRIDAY-ACCEPTANCE-STATUS.md`.

October 22 follow-on: real eight-worker app-transport checks pass, as do full-upgraded-schema pinned-call/call-vs-SMS overlap and identity immutability. Fresh production function/ACL fingerprints match the expected released Facebook-only delta. Full table/policy/constraint drift and live/operator acceptance remain open.

October 22 current-schema follow-on: fresh table/constraint/policy/index/trigger/view
and grant comparison passes with only the expected released Facebook delta. View
security/grants are now preserved in the restore and verified. Upgrade plus ten
intake journeys pass again (122.08 seconds). Separate real-role authorization checks
pass against current fingerprint-matching admin functions. Sending flag values still
need Vercel email verification; database scheduling remains paused. Continue with
import component coverage and operator acceptance while recipient identity is pending.

## October 22 import repair

- Fixed active land CSV truncation to preview five/save all; immutable manual-import
  receipts, explicit retry, exact property deduplication, parcel-conflict refusal,
  owned review tasks and history preservation pass actual SQL/API checks.
- Fixed the unmounted standalone lead importer to use server reconciliation and
  report uncertain outcomes; no browser insert or separate background model run.
- Twelve proposed migrations now pass the full upgrade/rollback rehearsal and ten
  intake journeys. Historical files remain unchanged. Nothing deployed.
- Backend 1,288 pass/10 skip; frontend 245 pass (52 files, maxWorkers=4); pipeline
  231 pass; build and lint gate pass (143 existing findings).
- Continue with main lead CSV ownership/concurrency, buyer/Master List coverage and
  large-land-list pagination/error handling. Detailed source/evidence and release
  limits: `MANUAL-LAND-IMPORT.md`. Live acceptance inputs and flag verification remain open.

## October 22 complete land visibility

- One complete, count-checked query now drives cards, funnel and filters; 25-card
  rendering, page navigation and search expose records beyond the API cap.
- Failed/changed/repeating reads cannot become partial totals or false empty states;
  failed refresh keeps last confirmed data with visible retry. Import receipt refresh
  updates the same cache. Dead records no longer enter comping.
- Nine regressions pass, including 1,003 simulated records; all 254 frontend tests
  across 53 files pass, with build/typecheck and lint gate (143 existing findings).
- Read-only production land aggregate is zero records. No production writes,
  schema, provider or scheduling changes. API/backend unchanged this step.
- Next: main CSV assignment/due task/concurrency; buyer/Master List UI coverage;
  operator/live acceptance. Details: `LAND-LIST-COMPLETENESS.md`.

## October 22 current production merge

Merged production a898151 into the isolated candidate; preserved production queue
recovery/tests, stronger view-aware restore, all upgrade modes, historical handoff
and both candidate deployment blocks. Backend 1,290/10 skipped and full twelve-file
upgrade/rollback, manual import and call/SMS concurrency plus ten journeys pass.
No production changes. See `PRODUCTION-BASELINE-MERGE.md` and continue the R8/live
work before any release approval.
