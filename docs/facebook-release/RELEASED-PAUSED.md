# Facebook-only release — October 20, 2026

The owner explicitly authorized PR #22 and its single migration, with live messages and schedules paused. Release and non-sending verification are complete. Controlled valid submissions, Meta lead retrieval, email delivery and SMS/handset testing remain unapproved.

## Deploy result

- Production URL: https://wholesale-automation.vercel.app
- Status: READY, promoted and verified by domain lookup.
- Deployment: `dpl_Dwjn7sjLUB5C9X2JsoezbSKjJ6go`.
- Released merge commit: `a89815126d9a98ced016167d8e383641d133135f`.
- PR: https://github.com/julysses/Wholesale-automation/pull/22 (merged).
- Framework: FastAPI backend with Vite frontend.
- Build duration: approximately 87 seconds, excluding queue time.
- Previous production deployment: `dpl_957SFZ7BF74hufEc25nUADWr3ryz`, commit `7b406f5c44a39fd8eec67bb7801c1d32c0526ea5`.
- The previous runtime and reviewed production base differed only in checkpoint documentation. The merged runtime is byte-identical to the locally validated candidate.

## Database release

Applied only source migration `20261020184154_facebook_inquiry_sms_receipts.sql`, with bounded lock/statement timeouts and preconditions for the original transport-protection function and disabled SMS schedulers. Supabase assigned deployed migration version **20261020192531**, name `facebook_inquiry_sms_receipts`. This is the same source migration, not an additional migration. Do not replay the source filename or repair history to force timestamp equality.

History advanced from 91 to 92 entries; comparison confirms exactly that one new migration. No county migration, directory-wide push, backfill, or empty-session reconciliation ran. The empty-session reconciliation function remains absent.

Before/after aggregate hashes match for all existing SMS jobs (excluding the newly added null column), SMS event receipts, Retell sessions and Retell turns. Native receipt count remains zero because no valid test inquiry was submitted. RLS, service-role insert/read access, browser-role denial, immutable receipt protection and validated source/identity constraints were verified.

## Pause controls

- `SMS_LIVE_ENABLED=false`, `EMAIL_LIVE_ENABLED=false`, `RETELL_SMS_LIVE_ENABLED=false` were explicitly set for the production deployment.
- AI calling and SMS nurture enable flags are absent and default false in the reviewed code.
- Both private Retell schedulers remain false; both Retell database cron jobs remain inactive.
- The existing Vercel SMS-nurture cron was discovered enabled and explicitly disabled at project level. It remains disabled after promotion.
- Production domain auto-assignment was disabled for staged verification and remains disabled, so a later build does not silently replace this reviewed deployment.
- Existing database retention and launch-monitor maintenance jobs were observed active and left unchanged. No collection schedule was enabled or executed.
- No SMS, email, Retell generation, Meta lead retrieval, worker invocation, or held-input replay was initiated by verification.

A merge-triggered preview build for the same SHA finished separately; it was not promoted. An attempted cancellation raced with its completion and returned not-cancelable. The production build was observed through its original deployment ID until READY; no replacement production build was created.

## Verification and limits

Both the staged deployment and public production alias passed nine non-sending checks:

| Check | Result |
| --- | --- |
| Public database/intake/owner readiness | 200 / ok |
| Hilltop website form configuration and HTML route | 200; 11 questions |
| Jays website form configuration and HTML route | 200; 8 questions |
| Empty submission to each website form | 422; required-field rejection before persistence |
| Facebook webhook verification with invalid token | 403; configured verification guard |
| Facebook webhook with missing/invalid signature | 403; configured signature guard |

Five additional unauthenticated GET checks confirmed the public readiness endpoint, both form configurations, and both form pages return 200 without login redirects. These check HTTP access and configuration; they do not constitute a rendered-browser acceptance test.

The first probe expected 400 for incomplete forms; inspection confirmed the application's intentional response is 422. Only the probe expectation was corrected; application behavior was not changed.

The ten complete HTTP/SQL journeys previously passed locally under the production-shaped schema and application service role, with mocked providers. Those results apply to the released runtime because its code is unchanged. **Production verification does not prove a valid lead has traversed the live Meta or website handoff.** That requires the separately approved controlled test. No production leads were fabricated for this release check.

## Post-deploy observability

A deployment-scoped, 15-minute error/fatal log-count query returned no groups. Availability/readiness returned ok. This is a narrow post-release observation, not ongoing monitoring or live delivery proof.

Supabase's security advisor reports an informational “RLS enabled, no policy” finding for the new server-only receipt table. This is intentional: browser roles have no privileges and service_role has only SELECT/INSERT; adding a browser policy would weaken this boundary. [Advisor explanation](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy). Three existing authenticated security-definer warnings concern other functions; they were not modified by this migration.

## Next authorized decision

Review this release and approve a separate, tightly scoped live acceptance run when ready. It should use fresh controlled leads for Facebook Instant Forms and both website forms, prove assigned ownership/tasks and real notification delivery, then verify provider callbacks, handset acknowledgment/reply, STOP/DNC suppression, and no replay. Keep schedules disabled throughout that test unless separately authorized. Ad traffic readiness remains unproven until those checks pass.

Rollback must retain native evidence and keep all messaging disabled. Do not blindly promote the old deployment: its environment snapshot predates the explicit email/SMS pause settings. Rebuild any rollback revision with the current disabled flags, retain the forward migration, and verify before promotion.

Evidence: `production-release.json`, `staged-intake-verification.json`, `production-intake-verification.json`, `public-access-and-pause.json`; reproducible non-sending probe: `scripts/release/verify_paused_intake.py`.
