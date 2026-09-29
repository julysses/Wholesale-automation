# Launch readiness continuation — September 28, 2026

Working branch: `codex/launch-runtime-checkpoint`; CRM PR #9 and website PR #3 are merged.
Decision: **website intake is live and verified; full automated launch remains gated by provider connection and delivery acceptance.**

## Full-launch checklist — September 28, 2026, 9:20 PM CT

Owner: Julio. Confirmed business/test phone **214-701-0100**, test email **julio@hilltophome.co**. Authorized scope includes website/Facebook intake, personal follow-up, SMS, email and AI calls. No ads activated or real seller outreach initiated.

| Launch requirement | Status | Evidence / next action |
|---|---|---|
| Database recovery | Done | Pro/Micro active; SQL and form queries working. Exact recovery cause not proven. |
| Public database protection | Done | Anonymous REST inserts into both intake tables fail 401/42501; validated server intake succeeds. |
| Database function/security settings | Done | Seven fixed search paths, public CREATE revoked from app roles, anonymous approval RPC denied; leaked-password protection enabled. |
| Admin helper protection | Verified with limits | Live authenticated unknown-user role/status changes denied; approval false. Guards require approved admin in profiles. Full signed-in operator UI acceptance still pending. |
| Website connection | Live | Missing WHOLESALE_API_BASE caused live 500; verified CRM default added. HilltopHome PR #3 merged at `ec682bf`. |
| Website contact and consent | Live | Correct214-701-0100 link/confirmation; optional SMS consent; phone validation and explicit success receipts. |
| Website dependencies | Done | Next.js 15.5.26 / React 19 / PostCSS 8.5.28; audit 0; tests, production build/type/lint passed. |
| Durable CRM intake | Live | PR #9 merged at `92c08f3`; Vercel production Ready/Current. Receipt is finalized atomically with lead and assigned task before success. |
| Recovery | Implemented | Admin-only POST /api/lead-gen/submissions/{id}/recover. Repeat finalization preserves one lead/task; no provider sends replayed. |
| Owner settings | Done | Julio's approved profile owns new tasks. Saved contact/agency settings; service-role SELECT on app_settings repaired. Vercel agency identity overrides updated. |
| STOP matching | Implemented and tested | Intake matches canonical US digits across shared registry and three lead phone fields; invalid/unknown results fail closed. Live carrier STOP webhook test still pending. |
| Live end-to-end acceptance | Passed | hilltophome.co browser -> CRM -> processed receipt05e83afc-dbaf-4648-9cc7-56796e7c629c -> leadaced76df-cc69-4f24-be82-8e946d26669d -> Julio task -> correct browser confirmation. |
| Automated SMS | Blocked on account setup | No Twilio/Telnyx/MessageBird credentials in Vercel or saved settings. Connect chosen account/sender and verify receipt, STOP and permitted-hours behavior using authorized number. The code has a Launch Control reply handler; a native Twilio inbound/status adapter is not yet wired and must be completed if Twilio is selected. |
| Email | Blocked on account setup | No SendGrid/Mailgun credentials or sender configured. PR #10 removes false success for unconfigured email and requires an explicit sender. Verify domain/sender and receipt at authorized email; finish independent after-hours owner alert acceptance. |
| AI calls | Blocked on account setup | No Retell credentials, agent, originating number or webhook secret. Verify channel permission, approved script, test call, transcript and signed completion webhook. |
| Facebook Lead Ads | Blocked on account setup | App/Page token, app secret and verification token missing. Verify native test lead, consent mapping, owner task/routing and signature rejection before enabling campaign. |
| Backup | Backup available | Dashboard physical backup September 29, 2026 at 01:30:08 UTC. Restore rehearsal to isolated destination not completed; no production restore attempted. |
| Deployment startup | PR #10 | Remove automatic historical migration replay from Railway startup; use explicit Supabase migrations. Git merge triggers three preexisting Railway services as well as Vercel; runtime status needs final check. |
| Historical incomplete receipt | Assigned for review | July10 receipt5255b3df-ee62-4d76-a2c1-ba0de2b37766 has no form ID/first name. Julio has a review task; no auto-recovery/contact. |
| Production operational acceptance | Pending | Signed-in CRM owner task/notification review, provider delivery, alert escalation/staffing and isolated restore exercise remain. HTTPS validates for apex and www (www redirects to apex); public form and health200; unauthenticated submissions API401. |

### Verification and test-data handling

- Backend 263 tests passed. Earlier unchanged frontend 91 tests, build and lint regression gate passed; release CI and Vercel preview passed.
- Isolated PGlite tests verified role restrictions, repeated migrations, receipt/lead/task transaction rollback, idempotency, and formatted shared STOP/secondary-phone suppression. These are not a complete staging restore.
- Live service-role tests verified settings access, finalizer repeat behavior and one assigned task. A new-lead transaction test was rolled back successfully.
- Five clearly labeled synthetic inquiries used only the authorized owner contacts. All five resulting test leads are marked dead/AI paused, sequences disabled, notes identify fixtures; their generated test tasks completed and notifications marked read. Owner phone was not globally suppressed.
- Final live notification metadata recorded seller_sms=no_consent_or_phone and owner_sms=failed_or_blocked. This is **not** provider delivery evidence.
- Security advisor remaining warnings concern intentionally authenticated guarded admin helpers/is_approved; webhook_jobs no-policy information reflects service-only access. Reference: https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable

### Resume and recovery runbook

1. Connect the user's chosen SMS, email, AI-call and Facebook accounts through signed-in dashboards or server-only secret fields. Never place service/provider keys in frontend variables, source or chat. The provider-account question is pending.
2. Verify provider delivery using +12147010100 / julio@hilltophome.co only. Retain provider IDs and callback/delivery outcomes. A dry run or accepted request does not establish delivery. Record separate consent evidence for each enabled channel; SMS consent does not itself prove AI-call permission.
3. For a saved but unfinished inquiry, inspect raw answers and processing status, then use the admin recovery endpoint. Recovery does not resend messages; reconcile uncertain provider receipts manually before any deliberate resend.
4. For app failure, use Vercel's previous known-good deployment. Keep additive database functions/permissions intact; do not restore anonymous writes as an app rollback. For database failure, use the Supabase backup controls and support case after assessing the restore point/data impact.
5. Inspect API health, form lookup, pending/failed submissions and assigned tasks after each release. A health200 alone is insufficient. Review the legacy receipt task separately.
6. Reconcile Supabase migration history by name/version before CLI deployment; the legacy custom _migrations runner must not run automatically. Repository timestamps created by CLI and provider-applied history timestamps can differ.
7. Complete isolated restore rehearsal and operating-owner acceptance, then explicitly record final all-channel go/no-go. Until provider tests pass, do not call the full automated launch complete.

## Earlier recovery checkpoint — historical

- User upgraded the organization to Pro and asked to continue recovery. Dashboard still showed Nano. Reviewed Nano-to-Micro change: same $0.01344/hour rate and **+$0.00/month**; applied only the Micro change. Spend cap and 8 GB disk remained unchanged. The resize completed and dashboard confirmed `t4g.micro`, Micro selected, 1 GB memory.
- A simple SQL query first succeeded before the resize, after the user's Pro upgrade; therefore the exact cause/timing of recovery cannot be attributed exclusively to Micro. Post-resize queries, migration history and security advisor checks also succeeded.
- Active `hilltop-home-co` form exists, ID `81f518b4-b115-4d6b-b339-d70d2c5d0d03`. Production form API returned HTTP 200 in 8.57 seconds initially, then 200 in 0.84 seconds on recheck. Browser rendered the headline and step-one fields. No form was submitted and no provider messages were sent.
- Health returned 200; unauthenticated scoring-status returned 401. Active-session inspection returned no other active queries at the sampled instant. This is point-in-time recovery evidence, not a load or soak test.
- Supabase history still lacks `protect_public_intake`. Verified both `public_insert_submissions` and `anon_insert_fb_leads` policies still permit anonymous INSERT. Apply the reconciled migration after isolated acceptance of the service-role intake path.
- Security advisor returned seven mutable function-search-path warnings, anonymous access to `is_approved`, authenticated security-definer notices for approval/admin helpers, and disabled leaked-password protection. The service-only `webhook_jobs` RLS/no-policy notice is informational; do not add public policies just to silence it. Review function bodies/permissions before changing helpers.
- PR #9 remains open; its current code checks and Vercel preview passed. No production code release, database migration, password change or support-ticket closure occurred. Earlier outage/support notes below are historical and superseded by these recovery checks.

Security remediation references: https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable and https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

## Earlier outage work — historical

- Pulled tracked branch successfully at `6cdcecd`; preserved existing untracked documentation.
- Rechecked Supabase project `dvzhzlipbwzzcliujzyz`: ACTIVE_HEALTHY in project inventory, but SQL, migration list, and security advisor queries time out. Postgres log query returned no rows; this does not establish database health or the root cause.
- Production `/api/health` returns 200; `/api/forms/hilltop-home-co` returns 404. The production build still masks database lookup failures as missing forms.
- Reran backend tests: 251 passed. Baseline frontend: 88 passed. Build, lint regression gate (157 existing findings), and npm audit (zero findings) passed.
- Added accurate public-form outage versus missing-form messages, a read-only retry button, 15-second config-fetch timeout, and request cleanup. All 91 frontend tests passed; updated build and lint regression gate passed. Commit `b539858` is pushed; GitHub backend/frontend checks and Vercel preview passed for this head.
- User initiated the Supabase restart. Dashboard and connector confirmed RESTARTING; the lifecycle API subsequently returned ACTIVE_HEALTHY, but the dashboard showed Unhealthy.
- Post-restart SQL failed twice with ECONNREFUSED to the database host on port 5432. At 2026-09-29 01:02 UTC, production form lookup still returned 404. Recovery is not established.
- Database observability could not load connection/disk/network metrics. Network restrictions page states all IP addresses can access the database; banned-IP retrieval failed with `Failed to fetch (api.supabase.com)` and directs the operator to support. No restrictions, passwords, compute sizes, or data were changed.
- Follow-up investigation: SQL again timed out. Postgres logs now returned authentication and statement timeout records. Infrastructure displayed 100% CPU, 46% memory and 100% disk I/O on Nano, with 0.31 GB used of 8 GB; exact metric time window and causality remain unconfirmed. Scaling requires a paid plan.
- Inspected managed upgrade: stable version 17.6.1.166 is offered alongside a preview; confirmation warns of up to one hour offline and no downgrade. Cancelled without applying because backup and preflight verification are unavailable. Support form is open with the correct wholesale project selected; authorization to send the prepared recovery request is pending. No support request has been sent.

## Earlier support escalation — historical

### Support escalation submitted

With explicit user authorization, submitted Supabase support request for `dvzhzlipbwzzcliujzyz`. Category: Database unresponsive; service: Database; severity: Normal (system impaired). Subject: `wholesale-automation database unreachable after restart — SQL timeout/ECONNREFUSED`. Supabase confirmed **Support request sent** and **Your ticket has been logged for wholesale-automation**; reply destination is `julyssesd@gmail.com`. No ticket number was displayed. Optional human/AI project-access grant was disabled. Await support response; submission is not evidence of database recovery.

1. Database query and form-read recovery are verified above. Retain the support case for root-cause analysis; no closure or further message was sent. Continue with the security/intake acceptance steps below, and recheck latency under controlled load before launch.
2. Reconcile current database policies/history against pending public-intake migration; use isolated acceptance before any rollout.
3. Trace the separate Netlify website intake into this CRM; verify contact number and optional SMS consent.
4. Finish durable submission recovery, operator role acceptance, owner assignment/alerts, and explicitly authorized provider delivery and STOP tests.
5. Review/release PR #9 only after remaining acceptance gates; verify the actual production deployment and intake afterward.

No live messages, calls, ad activation, schema changes, or deployment have been performed in this continuation. See `docs/hilltop-launch-hardening.md` for existing candidate fixes and `docs/hilltop-30-day-launch-plan.md` for the broader operating checklist.
