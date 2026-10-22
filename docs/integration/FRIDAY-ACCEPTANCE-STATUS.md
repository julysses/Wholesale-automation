## October 22 — manual buyer creation and consent defaults

New manual buyer creates now have stable references, private immutable receipts,
atomic creation and durable cancellation. New SMS/email consent defaults are false;
existing records remain unchanged. Browser drafts restore original details and
hold unknown saves; retries/cancel cannot duplicate or resurrect deleted buyers.
Backend1379/10skip, frontend342/63, build/lint/API-only pass. Nineteen-proposal
restore/rollback/ACL and real manual SQL/API races pass; ten intake journeys123.04s.
All nine Linux jobs passed in run39866097570 (711) at2a3d28c; PG17.11 restored
the exact catalog and passed all19/manual checks. CI backend1416/10skip/6subtests;
frontend342/63; native Vercel/Docker/API/pipeline/PG pass. See manual-buyer-ci-evidence.json. See MANUAL-BUYER-RECOVERY.md.
Manual edit/delete ambiguity, explicit classification/rescore, APN/volume/source,
operator/JWT/tenancy and buyer publication/carrier/live delivery gates remain open.
All nineteen proposals remain unapplied; no production/provider activation.

## Current release verification — October 22

Linux Docker runtime check and all seven jobs passed at93e27a4; runtime files remain
covered by that evidence until later changes. Current native Vercel API build candidate
1b6288e adds explicit API selector/native lock with all61 versions/hashes unchanged,
pinned builder25.1.3 and patched hash-pinned uv0.13.5. Local backend1379/10skip and
8 drift gates pass. Native Linux Vercel bundle CI run39861484224 passed all8 jobs. The exact mapped
6529-file function cold-start passed; all61 API versions and platform SDK match,
installer/bundle audits have0 known findings. CI backend1416/10skip/6subtests,
frontend327/62, API-only/Docker/pipeline/PG checks pass. See vercel-artifact-evidence.json. Production a898151 metadata now proves Python3.12,
timeout300s, memory2048MB, iad1. Effective sending flags still require dashboard
email verification. See VERCEL-RELEASE-ARTIFACT.md and its metadata/manifest.
Owner wording approval is complete. Public policy publication, paid registration,
carrier approval, handset reply/STOP and operator/source acceptance remain open.
All eighteen schema proposals remain unapplied; no production activation or deploy.
Earlier checkpoint counts/statements below are historical, superseded where noted.

## October 22 checkpoint — buyer enrollment and exact policy review

- [x] Separate public consumer form/privacy/terms routes outside operator login;
  default-off enrollment, reviewed policies and exact approved-version gating.
- [x] Administrator-only one-time private links, hashed capability, current-phone
  binding, seven-day expiry and immutable choices/receipts. No invitations sent.
- [x] Positive choices await administrator review with due task/notification;
  refusals immediately keep buyer SMS off and block later review of older positives.
  Review copies actual retained evidence and completes its task; DNC stays intact.
- [x] Public receipt recovery without replay, disabled-program recovery, private
  retained history and failed-save/correction UI. No SMS, email or phone verification.
- [x] Backend 1370/10 skipped; frontend 327/62 files; build/typecheck and lint gate
  pass (142 existing findings). Eighteen-proposal restore/rollback/ACL and real
  enrollment/API tests pass. Final intake timing is in the upgrade result.
- [x] Owner approved exact buyer policy wording/identity/privacy handling on October22.
  Exact copy/version retained in BUYER-SMS-APPROVED-WORDING.md and its program JSON.
- [ ] Publish the approved buyer policies and verify carrier domain/source proof.
  No buyer page has been published or enabled; fees and live sending are separate.
- [ ] Carrier registration/pricing approval, approved sender, handset delivery/
  reply/STOP, operator/JWT/tenancy, artifact/release/rollback and other Friday gates.

Read docs/integration/BUYER-ENROLLMENT.md. All eighteen migration proposals remain
unapplied; PR #21 stays draft and sending/schedules remain unactivated by this work.
No actual provider calls, purchases, live data changes or deployment.

## October 22 checkpoint — dedicated buyer SMS implemented, live acceptance open

- [x] Separate buyer route/configuration and private approval record; no homeowner
  sender fallback. No approved route or live configuration is seeded/enabled.
- [x] Immutable reservation/log before one-way final authorization, current written
  consent/DNC recheck, five-second non-retrying SDK, uncertainty holds, one attempt
  per number/day and shared-destination deduplication. Known result recovery never
  calls create again. Consent review and authorization share phone/row lock order.
- [x] Signed buyer callbacks bind saved route/recipient/reference/SID, preserve
  delivery/terminal conflicts and continue while sending is paused. Human replies
  retain history and assigned due tasks, including duplicate/owner/deletion recovery.
  Native or buyer STOP suppresses buyer eligibility; START never clears DNC.
- [x] Explicit UI readiness and full branded/STOP preview; consent inspection does
  not send. Failed/malformed readiness keeps sending disabled.
- [x] Backend 1,370/10 skipped; frontend 320/61 files; build/typecheck, API-only cold
  start and lint gate pass (142 existing findings). Seventeen-proposal apply,
  rollback/retention/ACL and ten local intake journeys pass (124.43 seconds).
  Final async callback path additionally passes a fresh buyer-only SQL rehearsal.
- [ ] Buyer SMS remains REQUIRED / NOT ACCEPTED: consumer enrollment and policy/
  terms coverage, priced registration approval, carrier-approved sender, actual
  handset receipt/reply/STOP, signed-in/JWT/tenancy and deployed artifact/rollback.

Read BUYER-SMS-TRANSPORT.md and its source manifest in docs/integration.
All seventeen migration proposals are unapplied; PR #21 remains draft. No real
provider messages, production mutations, paid registrations or sending activation.
The latest carrier review evidence does not establish a Friday buyer-SMS launch.
Other source/PropStream, volume/APN and manual CRUD/classification gates remain.

## October 22 checkpoint — buyer SMS consent and verified campaign limitation

Fresh signed-in Twilio evidence confirms only one campaign, Verified for homeowner
property inquiries; its description and opt-in flow exclude unrelated marketing.
Buyer deal alerts need separate approval. User sign-in is complete. No campaign,
service, number, opt-out configuration or production settings were changed.
Twilio's current quickstart estimates 10–15 days for review; next-day approval and
Friday buyer-SMS launch cannot be promised. Buyer SMS remains REQUIRED / NOT ACCEPTED.

- [x] Candidate administrator-only immutable written-consent review, saved original
  disclosure/action/source/hash/date and exact current phone; no automatic sends.
- [x] Buyer profile review/read screen, failed-read state, stable retry, local file
  fingerprinting and role/suppression visibility. Files stay on the device.
- [x] Real API/SQL confirms current roles, legacy boolean insufficiency, lost committed
  response recovery, changed phone/refusal/late replay, DNC, deletion retention,
  browser denial and an actual still-blocked buyer SMS request after consent review.
- [x] Backend 1,348/10 skipped; frontend 315/61 files; build/typecheck, lint gate
  (142 existing findings), API-only cold start, sixteen-proposal upgrade/rollback
  and ten local journeys pass (124.27 seconds). No real provider calls.
- [ ] Dedicated buyer SMS transport, signed receipts/replies/STOP, consumer enrollment,
  policy/terms coverage, priced sender/campaign approval, handset delivery and full
  signed-in release/artifact/rollback acceptance. Broad schedules stay paused.

See BUYER-SMS-CONSENT.md, BUYER-CAMPAIGN-REGISTRATION-DRAFT.md and
BUYER-SMS-LAUNCH-GATE.md in docs/integration. The registration draft is not ready
for submission: real enrollment/evidence, policy coverage, transport and concrete
purchase approval remain missing. PR #21 stays draft; sixteen proposals unapplied.

## October 22 checkpoint — durable buyer outreach; buyer SMS required

User requires buyer SMS for Friday October 23. Email-only launch does not meet the
brief. Buyer SMS remains blocked in this candidate while a separate buyer-consent,
suppression, durable claim and signed receipt/reply route is prepared. Do not reuse
property-inquiry consent or fabricate leads. Current provider campaign scope is
unverified; local Twilio settings are absent and the existing console is signed out (confirmed after the timeout).
Broad schedules remain paused. No production changes or real provider calls.

- [x] Save immutable per-request/per-buyer attempt and public history before email
  dispatch; stable retries, destination holds and ambiguous-result stops prevent
  automatic repeat sends. Explicit reconciliation reads saved receipts only.
- [x] Preserve history after buyer deletion; deny browser writes to saved history.
- [x] Bind signed SendGrid delivery events to app message ID and recipient. Keep API
  submission and event IDs separate. Opens/clicks do not imply delivery; conflicting
  terminal evidence holds for review. Buyer email replies remain unimplemented.
- [x] Real SQL tests cover eight competing sessions, lost claim/finish responses,
  rollback before dispatch, signed/wrong-recipient callbacks, retention and ACLs.
- [x] Backend 1,345 passed / 10 skipped; frontend 308 across 60 files; build/typecheck,
  API-only cold start and lint gate pass (142 existing findings). Full fifteen-
  migration rehearsal and ten connected local journeys pass with stubbed providers.
- [ ] Required buyer SMS implementation, verified sender/campaign scope, immutable
  buyer-specific consent and actual handset delivery/reply/STOP acceptance.

See `BUYER-OUTREACH-DURABILITY.md` and `BUYER-SMS-LAUNCH-GATE.md` in
`docs/integration/`. PR #21 remains draft; all fifteen migration proposals unapplied.

# Friday acceptance status — October 22

## Latest candidate scope — October 22

The forward allowlist now has fourteen unapplied proposals: the original eleven,
manual land repair, main CSV intake and a new atomic buyer CSV transaction. Buyer
imports now confirm complete data/log/receipt commits, support stable retry and
preserve buyer controls/consent. See `BUYER-CSV-TRANSACTION.md`,
`BUYER-READ-COMPLETENESS.md`, `CSV-LEAD-TRANSACTION.md` and `MANUAL-LAND-IMPORT.md`.
Backend 1,345 / frontend 303 / pipeline 231 pass, with build/typecheck and lint gate.
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
| R8 Retention and import | Pipeline and frontend regression suites pass | Land and standalone lead import regressions fixed; real SQL retries/concurrency/preservation pass. Main CSV API/UI, ownership, exact retry, concurrency and one-way AI claims/results pass locally. Bounded multi-batch AI recovery now passes with immutable checkpoints and an operator panel. Buyer list/history completeness and nullable preference edits now pass, including 1,003-row real-SQL reads. Atomic buyer CSV commits, consent preservation, lost-response recovery and competing imports now pass locally. Durable explicit classification/rescoring, manual-create ambiguity, actual buyer attempt/receipt/reply/retention coverage, APN event-history review, production-volume locks and signed-in operator review remain open. Complete land pagination/error recovery now pass. Saved buyer outreach visibility/error recovery now passes with 1,003 simulated rows; see `BUYER-OUTREACH-HISTORY.md` for missing backend evidence |
| R9 County/trace/scoring | Restricted ingress, trace caps and scoring concurrency pass; pipeline 231 tests | Current source completeness/PropStream end-to-end acceptance within existing spend cap |
| R10 Feature bundles | Real concurrent offer/property, lot and valuation checks pass on minimal fixtures | Full upgraded-schema call/SMS overlap now passes; remaining feature interactions and operator workflow acceptance |
| R11 Schema and access | Saved catalog with synthetic historical rows, fourteen proposed migrations, partial/full rollback, ACL assertions pass | Fresh shape comparison now matches the released baseline across tables, constraints, indexes, triggers, policies, views, view security and grants. Function delta matches the Facebook release. Exact release manifest/recovery review and production-volume locks remain open |
| R12 Frontend and release | 303 tests, build/typecheck and lint gate pass; candidate deployment disabled | Signed-in complete operator walkthrough, matching deployed API/schema, reviewed release artifact |

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
