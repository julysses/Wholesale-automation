# Final launch verification — October 8, 2026

Goal: complete each outstanding acceptance gate before declaring full automation launch-ready.

## Completed evidence
- Both websites' five intake intents reached CRM leads, Julio follow-up tasks, dashboard notifications and signed delivered owner emails on October 7. See website-intake-verification-20261007.md.
- Twilio approved campaign, registered sender and controlled outbound delivery are verified. Existing number ending0280 remains suppressed.
- Supabase latest completed physical backup observed October8 11:48:17UTC; prior daily backups visible.
- Added seven clock-boundary regression cases for the public SMS send path: before09:00 refused,09:00 allowed,18:59 allowed,19:00 refused; weekend outbound refused, inbound reply allowed during hours but refused at19:00. All25 Twilio tests pass (23 existing datetime deprecation warnings). These are mocked-provider tests, not live after-hours acceptance.

## Critical Meta recovery
- October7 production Page token was expired when checked October8. Do not consider Facebook intake healthy until a replacement is deployed and native retrieval succeeds.
- User approved longer-lived credentials for the same Page and existing permissions, plus isolated restore rehearsal.
- Meta debugger Extend Access Token returned 'This content is no longer available'. Followed current official guide via server-side exchange instead; extended user token valid through Unix1796584422, data access expires1799257318. Credential values are absent from this checkpoint and repository.
- Exact Page token derivation is blocked with Graph code200, 'API access blocked'. Meta app dashboard redirects to Developer Platform Blocked User Error: 'Account confirmation needed' due to unusual activity.
- Opened account confirmation, selected existing masked Hilltop email and requested code. User must enter code in Facebook confirmation tab1348645682. No replacement production credential saved and no new Meta deployment performed.
- After confirmation: derive exact Page1303115306222198 token, verify validity/lifetime/scopes, replace production Vercel FACEBOOK_ACCESS_TOKEN Secret, redeploy and verify native lead/task/owner delivery. Then real yes/no consent acceptance and recoverable retirement of old v1 form. Check Facebook consent receipt compatibility with SMS send guard before enabling seller SMS.

## Restore rehearsal handoff
- Additional isolated project cost reviewed and approved: compute$9.68 + disk$0.50 = $10.18/month while provisioned.
- Selected latest backup and prepared project name wholesale-restore-rehearsal-20261008 in original project backups restore-to-new-project UI tab1348645658.
- NOT started: final Create new project form requires a NEW database password. Computer-use policy requires user to enter and submit new credentials personally. User instructed to enter strong password and click Restore to new project. Production database has not been restored or altered.
- Once provisioned, record restored project ID and verify SQL/schema/data/permissions against backup timing. Storage objects/settings, Edge Functions, Auth settings/API keys and extension settings require separate reconfiguration. Prepare cleanup to stop added charges after rehearsal; do not delete project without required confirmation.

## Remaining launch gates
- [ ] Current authorized0100 real STOP callback, handset unsubscribe reply, CRM suppression and subsequent send refusal. SQL October8 still shows only prior inbound HELP and October7 outbound delivery.
- [ ] Secondary controlled mailbox supplied; real unsubscribe event and subsequent refusal, preserving primary owner-alert mailbox.
- [ ] Meta account confirmation, durable Page token deployment and successful native intake; real independent yes/no consent tests and old form retirement.
- [ ] Retell signup completed personally (password/Terms), then agent/number/script/security configuration and authorized live call/transcript/CRM completion.
- [ ] Isolated restore SQL verification, after-hours runtime acceptance and operational failure alerts.
- [ ] Final full-scope acceptance and approval to broaden recipient restrictions. Current SMS/email allowlists remain in place; no real seller contacted or paid ad started.

## Resume
CRM branch codex/twilio-live-integration; production branch claude/ai-wholesaling-agency-KkDF1. Pull before edits and push after each update. Preserve unrelated untracked docs/deployment-vercel 2.md and tasks/twilio-setup-20261006 2.md.
Browser handoffs: Meta confirmation1348645682; Supabase restore1348645658; Retell signup1348645664; Vercel secrets1348645459; Graph Explorer1348645503. Redact all credential observations; no unredacted credential screenshots. Evidence screenshots in task outputs: meta-account-confirmation-20261008.jpg and restore-password-handoff-20261008.jpg.
