# Full production acceptance — active October 7, 2026

Goal: finish all remaining setup and prove readiness for the authorized website/Facebook intake, SMS, email, AI calls and owner follow-up scope. A green deployment or one delivered email is not full acceptance.

## Current evidence
- SendGrid authenticated domain/link branding verified; restricted v2 key stored as Vercel production Secret; original revoked. First local EmailClient email received by Julio.
- Signed SendGrid callback deployed at commit 90abc47. SendGrid Test Integration persisted 11 sample event types for example@test.com. Sample bounce/unsubscribe suppression persisted. Unsigned production request returned 401. These are provider-generated sample events, not real delivered-message callbacks.
- Email claims and receipts are service-only with RLS; SQL rollback assertions verified duplicate-send refusal and suppression. Admin test/evidence controls added to SetupWizard Email step.
- EMAIL_LIVE_ENABLED=true with EMAIL_ALLOWED_RECIPIENTS=julio@hilltophome.co ONLY. Deployment dpl_9SqiZy2KiJw8MDu9x99ZNCuq2fRs reached READY. This is restricted test mode, not a broad email launch.
- Backend 337 tests passed, then 42 focused tests passed after two new auth cases. Frontend 96 tests, TypeScript/Vite build, lint regression gate passed; 157 baseline lint findings remain.
- Nine later-added SQL functions now have fixed pg_catalog,public,pg_temp search paths. Applied explicit migration lock_launch_function_paths. Query confirms all nine and no public-schema CREATE for app roles. Advisor mutable-search-path warnings gone. Three guarded admin helper warnings require continued contextual review; server-only no-policy notices are intentional.
- Twilio HELP/STOP user confirmations and CRM suppression previously verified. Application-originated outbound carrier delivery is still unproven. SMS_LIVE_ENABLED remains false.

## Required acceptance work — not complete
1. **Production email:** user must sign in to opened https://wholesale-automation.vercel.app/login with approved admin. Asked asynchronously. Then SetupWizard Email step -> Send production test email; match email_messages, real signed processed/delivered callbacks and inbox receipt. Check duplicate test reference does not resend.
2. **Unsubscribe:** configure visible email unsubscribe mechanism for intended seller/buyer mail; verify real unsubscribe event and subsequent send refusal. Do not globally suppress Julio's primary notification mailbox without planning the test/recovery and explicit renewed consent. Sample events and SQL assertions are not real unsubscribe acceptance.
3. **Twilio outbound:** fresh live campaign approval check; add exact test-recipient restriction before enabling; use authorized +12147010100 only with matching consent receipt; verify provider SID, actual handset receipt, signed delivered callback, STOP and refusal. Keep phone ending0280 suppressed.
4. **Lead handoff:** production website form -> durable receipt -> one lead -> Julio task -> dashboard notification and authorized owner email, including SMS-declined case and after-hours handling. Archive only clearly labeled fixtures.
5. **AI calling:** inspect current Retell credentials/agent/number/script/webhook security, configure missing pieces; controlled authorized call + transcript + signed completion + CRM routing. Never infer readiness from SMS/email.
6. **Facebook intake:** inspect app/Page connection and native lead test; verify signature and consent mapping, deduplication, owner assignment. No paid ads started.
7. **Operations/recovery:** signed-in operator acceptance, alert routing, latest backup and isolated restore rehearsal, actual Vercel/Railway runtime roles and provider gates, remaining database admin-helper guards. Do not restore over production.
8. **Final audit:** every requirement above has current evidence; only then remove recipient restrictions / enable appropriate campaigns. Do not label the full system production-ready with any required gate outstanding.

## Resume pointers
Repo branch codex/twilio-live-integration; production claude/ai-wholesaling-agency-KkDF1. Pull before edits, push after updates. Preserve two unrelated untracked docs with ` 2.md` suffix.
Browser Chrome 3: CRM tab1348645462, SendGrid tab1348645447, Vercel tab1348645459. Never capture unredacted credentials in AX/screenshot output. Detailed email history: tasks/sendgrid-connection-20261007.md; Twilio: tasks/twilio-live-integration-20261006.md; original broader checklist: tasks/launch-readiness-20260928.md.
