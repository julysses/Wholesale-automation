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
1. **Production email:** real website-triggered owner alert accepted and signed processed/delivered callbacks persisted (details below). Await user inbox/unsubscribe-link confirmation. User must still sign in to production CRM for operator UI acceptance and the admin test duplicate-reference check.
2. **Unsubscribe:** SendGrid Subscription Tracking configured and enabled. Verify rendered link, real unsubscribe event and subsequent send refusal using an authorized test mailbox. Do not globally suppress Julio's primary notification mailbox without planning the test/recovery and explicit renewed consent. Sample events and SQL assertions are not real unsubscribe acceptance.
3. **Twilio outbound:** live campaign Verified, sender attached, exact recipient restriction deployed; enable restricted SMS test mode and use authorized +12147010100 only with matching consent receipt; verify provider SID, actual handset receipt, signed delivered callback, STOP and refusal. Keep phone ending0280 suppressed.
4. **Lead handoff:** production website form -> durable receipt -> one lead -> Julio task -> dashboard notification and authorized owner email, including SMS-declined case and after-hours handling. Archive only clearly labeled fixtures.
5. **AI calling:** inspect current Retell credentials/agent/number/script/webhook security, configure missing pieces; controlled authorized call + transcript + signed completion + CRM routing. Never infer readiness from SMS/email.
6. **Facebook intake:** inspect app/Page connection and native lead test; verify signature and consent mapping, deduplication, owner assignment. No paid ads started.
7. **Operations/recovery:** signed-in operator acceptance, alert routing, latest backup and isolated restore rehearsal, actual Vercel/Railway runtime roles and provider gates, remaining database admin-helper guards. Do not restore over production.
8. **Final audit:** every requirement above has current evidence; only then remove recipient restrictions / enable appropriate campaigns. Do not label the full system production-ready with any required gate outstanding.

## Resume pointers
Repo branch codex/twilio-live-integration; production claude/ai-wholesaling-agency-KkDF1. Pull before edits, push after updates. Preserve two unrelated untracked docs with ` 2.md` suffix.
Browser Chrome 3: CRM tab1348645462, SendGrid tab1348645447, Vercel tab1348645459. Never capture unredacted credentials in AX/screenshot output. Detailed email history: tasks/sendgrid-connection-20261007.md; Twilio: tasks/twilio-live-integration-20261006.md; original broader checklist: tasks/launch-readiness-20260928.md.

## October 7 continuation — unsubscribe and owner follow-up
- GitHub writes recovered. Both production and working branches pushed through 5903e0c; backend/frontend CI passed and Vercel dpl_7ifU55gomNqFLXnX5Z2ChVynoBsu reached READY.
- SendGrid Subscription Tracking enabled and saved successfully; default HTML/plain-text unsubscribe content retained, blank replacement tag appends it to every message. Real click/event/refusal still pending.
- Added SMS_ALLOWED_RECIPIENTS guard, 18 Twilio tests passed. Production Vercel Config saved as +12147010100 only. SMS_LIVE_ENABLED remains false. New deployment required to load the new variable.
- Fresh Twilio dashboard: campaign CM81b71bfdf3483a566e6ecf0161c840b9 Verified/A2P Compliant; sender pool contains +14698049920. Inbound/status URLs still point to the production native handlers.
- Found internal owner SMS incompatible with this seller-inquiry campaign. Routine owner alerts now use EmailClient with a deterministic message ID, independent of seller SMS consent/hours/score; outcome and message ID persist in the operator notification. Seller SMS remains separately gated. Full backend suite: 348 passed.
- Added production NOTIFICATION_EMAIL=julio@hilltophome.co. This and SMS allowlist take effect with the next deployment.
- Vercel searches found no RETELL or FACEBOOK variables; app_settings contains no Retell/Facebook/VAPI/Air credentials. These integrations still require account access/configuration and real acceptance tests.
- Vercel environment connector returned403; CLI had no credentials and its login wait was canceled. Used existing signed-in Vercel UI successfully.
- CRM login tab was no longer open. Reopened production /setup, redirected to /login, and asked user to sign in. Current handoff tab1348645466.
- Screenshots in task outputs: sendgrid-unsubscribe-enabled.jpg, sms-test-allowlist.jpg, twilio-campaign-verified.jpg.
- Next: deploy owner alert change with current environment; controlled website inquiry with SMS declined -> durable lead/task/notification plus real SendGrid delivered callback; then signed-in admin acceptance, real unsubscribe test, controlled outbound SMS. Full AI/Facebook/recovery gates remain open.

## Verified production website-to-email acceptance — 12:23 PM Central
- Released d5af18797eeb0892bf275f63625437b6fa956c87 to both branches. Vercel production dpl_Mw1Q5xmnVdxkrMrwaBsMxzew1h9J READY; backend and frontend CI checks successful.
- Browser submitted a clearly labeled synthetic inquiry at hilltophome.co/get-an-offer using the authorized owner phone/email. Other reason, flexible timeline, good condition, owner occupied; SMS consent left unchecked. Browser displayed successful confirmation.
- Submission b5989183-c956-4002-b6ea-e56972b40b71 processed; lead9b99ad33-8a53-4d65-984d-3aee2bc59a90; exactly one task, assigned to Julio's approved profile89f3b3f6-5a88-4b79-b3f4-461e0cd626a2 (login julio@thejaysdallas.com).
- Notification7e120a1e-1de7-50f6-9a1e-ea66bd334bb8 records seller_sms=no_consent_or_phone, owner_sms=not_supported_for_registered_campaign, owner_email=accepted.
- Durable email c4b03c76-73ee-5622-9853-f3c44c5a8c31 -> julio@hilltophome.co, subject New lead — Launch Verification 20261007 Email Only. Provider ID pw9KhygKRimPTXSAMm89nA.
- Real signed processed callback17:23:17UTC and delivered callback17:23:18UTC stored against the same message ID. Zero SMS events for the fixture. This is production provider delivery evidence, not sample-event or local-send proof.
- Asked user to confirm inbox receipt and visible unsubscribe link; no unsubscribe click requested yet. CRM sign-in remains pending. Retained QA task for operator acceptance; fixture AI paused and both sequences disabled, with explicit test-only note. No DNC flag added to the owner number.
- New proof screenshots: website-production-acceptance.jpg and owner-email-configured.jpg. Checkpoint is authoritative; earlier missing-email/no-production-delivery statements are superseded by this evidence.
