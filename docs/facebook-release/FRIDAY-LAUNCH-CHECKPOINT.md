# Friday launch checkpoint

Updated October 21, 2026, America/Chicago. Target: Friday October 23.
Status: preparation in progress; live acceptance and full operational readiness not certified.

## Exact source and release

Active checkout: `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app`.
Branch: `codex/facebook-release-candidate`; starting HEAD `4480112c47096c6425b23d88dafaf4bccc7e8ef4`.
Copied from the verified October 20 Facebook release checkout, preserving Git history; origin is `https://github.com/julysses/Wholesale-automation.git`. Pulled upstream: already current. This is not a reconstruction of the older unpublished remote candidate.

Vercel live read confirms production deployment `dpl_Dwjn7sjLUB5C9X2JsoezbSKjJ6go` READY, commit `a89815126d9a98ced016167d8e383641d133135f`. Candidate differences before this checkpoint were documentation and verification tooling, not runtime code. This update changes only verification tooling and evidence.

## Fresh evidence

- Production Facebook receipt table exists and migration history contains `20261020192531` / `facebook_inquiry_sms_receipts`. Do not reapply.
- Approved configured intake owner exists.
- Native and app SMS scheduler flags false; both Retell cron jobs inactive. Retention and launch monitoring cron jobs remain active; do not describe all cron as disabled.
- One existing Retell API session remains `review`. No recovery or replay performed.
- Nine non-sending intake probes passed: readiness, both form configurations/pages, both incomplete-input rejections, invalid Facebook verification token and invalid signature rejection. Evidence: `evidence/2026-10-21-paused-intake.json`.
- Vercel CLI initially refused the noninteractive probe without confirmation. Added `--yes` before curl passthrough arguments; all nine probes then passed. No valid inquiry or provider call was made.
- Browser: app root reaches sign-in; Hilltop step-one form renders; Jays form renders with SMS consent unchecked. This does not prove signed-in operator flows or the external website-to-CRM handoff.

## Local verification on this exact release checkout

| Check | Result | Limit |
| --- | --- | --- |
| Backend | 1,131 passed, 10 skipped, 367 warnings | The ten journey tests require separate database runner |
| Frontend | 179 passed across 42 files | Component tests |
| Pipeline | 196 passed | Offline fixtures |
| Production build | Passed | Existing chunks above 500 kB warning |
| Lint regression | No new findings; 147 existing | Not clean lint |
| Separate PostgreSQL journeys | All 10 passed | Mocked providers; synthetic local data |
| Catalog restoration | 100 tables, 120 functions, 384 constraints, 27 triggers, 127 policies | Saved production-shaped catalog, zero production rows copied |
| Migration rehearsal / contention | Passed rollback and eight-worker contention; one receipt/job/ack claim, zero provider calls | Isolated PostgreSQL only |

Raw logs: `logs/launch-backend.log`, `launch-frontend.log`, `launch-pipeline.log`, `launch-build.log`, `launch-lint.log`, `launch-journeys.log` (ignored local files). PostgreSQL required sandbox escalation for shared memory; the disposable runner completed successfully and stopped its cluster. Real acknowledgment delays explain the approximately two-minute journey test duration.

Dependencies reused from existing local installations. `.venv` is an ignored local symlink; frontend dependencies were copied. The inherited tracked pipeline dependency symlink remains unchanged. This is not a clean dependency-install reproducibility result.

## Intake audit and monitoring

Read-only aggregate audit: Hilltop 17 submissions, Jays 22, one legacy unmatched submission. Three Hilltop submissions link to unassigned leads; two lack any task. All three affected leads have active reporting exclusions. Do not manufacture customer follow-up or remove exclusions to clear the audit. Review exclusion reasons before further classification.

One July 10 pending submission lacks a form configuration and lead; investigate provenance without replaying it. Native Facebook receipt count is zero, so no live native intake acceptance is established.

Open launch-monitor incident counts: form_sms 3; intake 1; intake_alert 1; retell_api_session 1; retell_api_turn 1; sms 2. Categorize current vs historical/held incidents before the release decision. Do not resolve incidents merely to make the dashboard green.

## User test preference and next actions

User chooses the same previously used phone number. Asked for its last four digits and confirmation of the same owner email inbox to bind the test to explicit owner identity. Do not infer the number from latest lead, clear DNC, bypass contact cooldowns, or reuse/reconcile the held session. Determine whether all three source tests can safely use this number; record any coverage blocked by the existing session or suppression. Same-number preference does not authorize recovery of historical work.

1. Verify recipient identity/history and design the exact supported one-number procedure; keep fresh inquiries and held work separate.
2. Check external Hilltop/Jays website routing, selected Meta form and disclosure/subscription configuration, effective messaging flags and Vercel outbound schedule state. The database flags alone do not prove environment flags.
3. Complete signed-in operator acceptance, role/workspace checks and investigate unresolved intake/monitoring evidence. Review rollback and alert ownership.
4. Run already-authorized bounded live tests only with exact fresh job scope and confirmed owner destinations. Obtain handset and inbox confirmation, reply and STOP evidence. Schedules remain paused pending owner review.
5. Keep broader app scope visible: PR #21 county/offer/lot/valuation integration remains draft and requires its own eleven-migration rehearsal and feature acceptance. Nothing here certifies those features or silently excludes them from the overall launch goal.
6. Publish readiness evidence and remaining blockers against Friday's target. Do not equate passing local tests or deployment READY with complete go-live readiness.

No production records, messaging flags, providers, schedules or migrations were changed in this session. No messages were sent. This checkpoint and tooling fix may be pushed to the existing release-candidate branch, whose Vercel deployment is explicitly disabled; use `[skip ci]`.
