# Launch readiness continuation — September 28, 2026

Working branch: `codex/hilltop-launch-hardening`; review: PR #9.
Decision: **database connectivity recovered; live launch remains gated** by intake security and integration acceptance.

## Full-launch checklist — current work

Confirmed scope: website/Facebook intake, personal follow-up, automated SMS, email and AI calls. Julio owns intake; business/test phone +12147010100 and test email julio@hilltophome.co explicitly authorized by user.

- [x] Database connectivity recovered after Pro upgrade; Micro configured.
- [x] Website repository located: julysses/HilltopHome; server route forwards to validated CRM API.
- [x] Live seven function search paths fixed; public-schema CREATE revoked from public/anon/authenticated; anonymous is_approved execution removed while authenticated execution retained.
- [x] Live form SMS checkbox made optional; remaining question order/settings preserved.
- [x] Supabase leaked-password protection enabled; security advisor confirms warning cleared.
- [x] Isolated PGlite role checks passed for public-intake restriction and security/consent migration. This is an isolated SQL test, not a full restored staging system.
- [ ] Apply public-intake restriction after verifying production server credential path. Existing migration tested: anon writes denied, service-role writes and operator reads preserved.
- [ ] Website candidate: correct phone, optional consent, explicit receipt checks and bounded requests; Next 15.5.26/React19 security upgrade, PostCSS8.5.28 override. Initial production build/type/lint passed and audit0; final build pending after route updates. Branch codex/launch-intake-fixes.
- [ ] Durable intake/recovery, assigned owner task, phone-normalized suppression, form confirmation setting respected.
- [ ] Approved/pending/operator role acceptance and admin helper guard checks.
- [ ] Production deployment/settings: Vercel login requested. Connector get_project has schema mismatch; CLI uncredentialed. No secrets requested in chat.
- [ ] Controlled SMS delivery + STOP/after-hours acceptance, email delivery, AI call/recording/webhook acceptance at authorized contacts.
- [ ] Facebook signature/lead test and campaign routing.
- [ ] Website release + CRM PR9 release, live browser/API acceptance, HTTPS/phone check.
- [ ] Backup/restore evidence, monitoring/recovery runbook, final go/no-go.

Security advisor after live changes: remaining warnings are three intentionally authenticated SECURITY DEFINER helpers (admin role/status setters and is_approved); acceptance of guards pending. webhook_jobs no-policy info reflects service-only access. No provider sends or ad activation performed in this checkpoint.

## Latest checkpoint — Pro and Micro recovery

- User upgraded the organization to Pro and asked to continue recovery. Dashboard still showed Nano. Reviewed Nano-to-Micro change: same $0.01344/hour rate and **+$0.00/month**; applied only the Micro change. Spend cap and 8 GB disk remained unchanged. The resize completed and dashboard confirmed `t4g.micro`, Micro selected, 1 GB memory.
- A simple SQL query first succeeded before the resize, after the user's Pro upgrade; therefore the exact cause/timing of recovery cannot be attributed exclusively to Micro. Post-resize queries, migration history and security advisor checks also succeeded.
- Active `hilltop-home-co` form exists, ID `81f518b4-b115-4d6b-b339-d70d2c5d0d03`. Production form API returned HTTP 200 in 8.57 seconds initially, then 200 in 0.84 seconds on recheck. Browser rendered the headline and step-one fields. No form was submitted and no provider messages were sent.
- Health returned 200; unauthenticated scoring-status returned 401. Active-session inspection returned no other active queries at the sampled instant. This is point-in-time recovery evidence, not a load or soak test.
- Supabase history still lacks `protect_public_intake`. Verified both `public_insert_submissions` and `anon_insert_fb_leads` policies still permit anonymous INSERT. Apply the reconciled migration after isolated acceptance of the service-role intake path.
- Security advisor returned seven mutable function-search-path warnings, anonymous access to `is_approved`, authenticated security-definer notices for approval/admin helpers, and disabled leaked-password protection. The service-only `webhook_jobs` RLS/no-policy notice is informational; do not add public policies just to silence it. Review function bodies/permissions before changing helpers.
- PR #9 remains open; its current code checks and Vercel preview passed. No production code release, database migration, password change or support-ticket closure occurred. Earlier outage/support notes below are historical and superseded by these recovery checks.

Security remediation references: https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable and https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

## Completed this session

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

## Resume steps

### Support escalation submitted

With explicit user authorization, submitted Supabase support request for `dvzhzlipbwzzcliujzyz`. Category: Database unresponsive; service: Database; severity: Normal (system impaired). Subject: `wholesale-automation database unreachable after restart — SQL timeout/ECONNREFUSED`. Supabase confirmed **Support request sent** and **Your ticket has been logged for wholesale-automation**; reply destination is `julyssesd@gmail.com`. No ticket number was displayed. Optional human/AI project-access grant was disabled. Await support response; submission is not evidence of database recovery.

1. Database query and form-read recovery are verified above. Retain the support case for root-cause analysis; no closure or further message was sent. Continue with the security/intake acceptance steps below, and recheck latency under controlled load before launch.
2. Reconcile current database policies/history against pending public-intake migration; use isolated acceptance before any rollout.
3. Trace the separate Netlify website intake into this CRM; verify contact number and optional SMS consent.
4. Finish durable submission recovery, operator role acceptance, owner assignment/alerts, and explicitly authorized provider delivery and STOP tests.
5. Review/release PR #9 only after remaining acceptance gates; verify the actual production deployment and intake afterward.

No live messages, calls, ad activation, schema changes, or deployment have been performed in this continuation. See `docs/hilltop-launch-hardening.md` for existing candidate fixes and `docs/hilltop-30-day-launch-plan.md` for the broader operating checklist.
