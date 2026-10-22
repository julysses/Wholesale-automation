# Friday acceptance status — October 22

## Latest candidate scope — October 22

The forward allowlist now has fourteen unapplied proposals: the original eleven,
manual land repair, main CSV intake and a new atomic buyer CSV transaction. Buyer
imports now confirm complete data/log/receipt commits, support stable retry and
preserve buyer controls/consent. See `BUYER-CSV-TRANSACTION.md`,
`BUYER-READ-COMPLETENESS.md`, `CSV-LEAD-TRANSACTION.md` and `MANUAL-LAND-IMPORT.md`.
Backend 1,345 / frontend 295 / pipeline 231 pass, with build/typecheck and lint gate.
No production schema, runtime, schedules or providers changed.

Target: October 23, 2026. This is a requirement review checkpoint, not go-live certification.
The original requirements remain in `WholesaleOS-Integration-Assessment.md` R1–R12.

| Gate | Current evidence | Remaining proof |
| --- | --- | --- |
| R1 Intake durability | Ten connected API/SQL journeys on upgraded saved catalog; both website boundaries checked | Fresh live source receipt, owner inbox and handset confirmation |
| R2 Consent integrity | Backend, frontend and pipeline suites pass; no-consent journeys refuse sending | Live Meta disclosure/form mapping and current website revisions |
| R3 Suppression | STOP/no-replay journeys pass; existing suppression suites pass | Verify exact shared recipient history; controlled live STOP/reply acceptance |
| R4 Dispatch ownership | Eight-worker Facebook receipt/job claim check passes; transport suites available | Eight-worker app transport and full-upgrade call/SMS overlap now pass; live exact job scope remains to verify |
| R5 Provider receipts | Connected mocked receipt and duplicate/out-of-order suites pass | Actual bound carrier delivery/callback and owner handset evidence |
| R6 Pause and expiry | Upgraded synthetic scheduler pauses retained; disabled/expiry suites pass | Database schedulers and outbound cron freshly confirmed paused; effective runtime flags require Vercel email verification before bounded live scope |
| R7 Tasks and alerts | Connected reply tasks, notification and mocked email journeys pass | Owner confirms real email, task and CRM history during live tests |
| R8 Retention and import | Pipeline and frontend regression suites pass | Land and standalone lead import regressions fixed; real SQL retries/concurrency/preservation pass. Main CSV API/UI, ownership, exact retry, concurrency and one-way AI claims/results pass locally. Bounded multi-batch AI recovery now passes with immutable checkpoints and an operator panel. Buyer list/history completeness and nullable preference edits now pass, including 1,003-row real-SQL reads. Atomic buyer CSV commits, consent preservation, lost-response recovery and competing imports now pass locally. Durable explicit classification/rescoring, manual-create ambiguity, outreach-log completeness, APN event-history review, production-volume locks and signed-in operator review remain open. Complete land pagination/error recovery now pass |
| R9 County/trace/scoring | Restricted ingress, trace caps and scoring concurrency pass; pipeline 231 tests | Current source completeness/PropStream end-to-end acceptance within existing spend cap |
| R10 Feature bundles | Real concurrent offer/property, lot and valuation checks pass on minimal fixtures | Full upgraded-schema call/SMS overlap now passes; remaining feature interactions and operator workflow acceptance |
| R11 Schema and access | Saved catalog with synthetic historical rows, fourteen proposed migrations, partial/full rollback, ACL assertions pass | Fresh shape comparison now matches the released baseline across tables, constraints, indexes, triggers, policies, views, view security and grants. Function delta matches the Facebook release. Exact release manifest/recovery review and production-volume locks remain open |
| R12 Frontend and release | 295 tests, build/typecheck and lint gate pass; candidate deployment disabled | Signed-in complete operator walkthrough, matching deployed API/schema, reviewed release artifact |

Frontend dependencies: Vite 6.4.5, Vitest 4.1.12, follow-redirects 1.16.1;
clean installation audits report zero vulnerabilities. Pipeline installation audit
also reports zero. Separate Python candidate audits now report zero known findings
for 84 root, 61 API and 29 isolated audit-tool packages, with complete hash-pinned
locks and fresh installs. The clean root suite passes; API-only cold start/access
checks pass. This is not a full app security audit or a deployed-artifact check.
See `PYTHON-DEPENDENCY-SECURITY.md` and its JSON evidence.

Sources: `production-upgrade-result.json`, `feature-concurrency-result.json`,
`FRIDAY-UPGRADE-REHEARSAL.md`, local ignored logs, release checkpoint in the sibling
`app` checkout. Test totals prove executed suites, not every original requirement;
remaining proof must be inspected before marking any broad gate complete.

Controlled live tests are already authorized. Recipient identity (last four digits)
and owner inbox confirmation are pending. The same-number preference does not
permit clearing DNC or replaying held sessions. Broad schedules stay paused pending
owner review. No production data, schema, messaging flags or deployments changed
in this checkpoint.

## October 22 schema and authorization review

Fresh production schema comparison passes against the locally restored catalog
plus the released Facebook migration. The restore now includes production view
security and grants, which were missing from the original saved catalog fixture.
The full upgrade, pinned-call/SMS overlap and ten intake journeys still pass.

Supabase's security advisor reports 33 INFO items for RLS tables with no policies,
plus three WARN items for authenticated SECURITY DEFINER entry points. The three
functions are `admin_set_user_role`, `admin_set_user_status` and `is_approved`.
Reviewed current fingerprint-matching bodies use approved-admin/profile checks.
Actual local PostgreSQL role checks reject approved ordinary users, pending users,
pending/denied/suspended admins, absent identity, anonymous RPC access and forged
user metadata. Approved-admin mutations and notification audit succeed. These
checks exercise database authorization with the local Auth UID stub; they do not
replace production Auth/JWT verification or a full tenancy review.

The RLS-without-policy items include deliberately service-owned scheduler/receipt
facilities; no policy was added to make the advisor quiet. Advisor findings are
preserved for review, not marked resolved. Guidance:
[authenticated definer functions](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
and [RLS without policy](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).

Vercel environment reads remain incomplete: connector permission 403, CLI refresh
failed DNS, and revealing a Config value in the existing dashboard required email
verification. No code was requested and no flag, schedule, deployment or production
row was changed. The pre-existing dashboard redeploy toast was not acted on.

October 22 land visibility follow-up: complete cards/funnel pagination, search,
25-card rendering, partial-read refusal, last-confirmed refresh recovery and import
cache consistency pass nine new regressions. All 254 frontend tests (53 files),
build and lint gate pass. See `LAND-LIST-COMPLETENESS.md`.

October 22 production reconciliation: current production a898151 was merged into
the paused candidate after seven conflict resolutions. Its native queue recovery
and two extra concurrency cases are retained. Backend now 1,290 pass/10 skip;
the twelve-migration upgrade and ten journeys pass again (122.64 seconds).
See `PRODUCTION-BASELINE-MERGE.md`. GitHub mergeability must be read back after push;
that does not close the remaining business/live acceptance gates.
