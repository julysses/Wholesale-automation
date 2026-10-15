## Production credential approval fulfilled — October15,2026

Owner explicitly approved production API/signing/scheduler credentials. Saved existing Retell key as Production RETELL_SMS_API_KEY; aligned Production RETELL_WEBHOOK_SECRET; saved new Production CRON_SECRET and matching encrypted production Vault retell_sms_worker_bearer. No secret values/files/logs/git. Do not ask again for this scope.

Credential deployment dpl_3jedu2s9tqHe4UTu1Y4D5svPoi2r READY. Production pg_net checks: request1 invalid bearer401; request2 valid200 connected=true, dispatch_authorized=false; normal worker request3 returned200 processed=0,sending_enabled=false. Retell built-in callback Test visibly reported success. No SMS/calls created; this is connection verification, not delivery evidence.

Published Retell V1 Production website SMS - SENDING OFF with callback https://wholesale-automation.vercel.app/webhooks/retell. V0 rehearsal preserved; editable draft now V2. Config saved Production RETELL_SMS_AGENT_ID=agent_193fc3ebd9844b50d54352f200, VERSION=1, FROM_NUMBER=+14698049920, SENDER_NAME=the automated assistant. Deployment dpl_8GuNAwL4TWNKmGqcS4HABrJavfZC verified READY on production aliases with those config values. All activation flags remain false/unset and scheduler/cron inactive. No phone agents assigned.

Both website repository handlers default to production CRM: Hilltop /api/get-offer -> /api/forms/hilltop-home-co/submit; Jays /api/intake sell -> /api/forms/the-jays-dallas/submit. Deliberately invalid non-contactable live submissions returned upstream422 (Hilltop) and email-validation422 (Jays); no leads/messages created. This verifies upstream validation, not successful intake/delivery. Environment overrides still possible; actual owner receipt must be observed in production.

Next: owner identifies their own form submission while sending OFF, so phone is captured through website as requested. Do not guess owner from latest lead. Verify successful receipt/consent/CRM notification before scoped sending. Build finite owner-only testing for both forms without disabling global cooldowns or DNC. Existing prior accepted chat guard and 24h cooldown block same-phone second test. Provider-native reply redirect compatibility remains unproven; routing flag OFF. Verify actual chat delivery/reply/STOP under bounded owner test, then disable test again. Do not claim one-minute handset delivery is ready or guaranteed.

Screenshots in chat outputs: production-retell-callback-success.png and production-scheduler-vault-saved.png. User approval is complete, not a remaining blocker.

## Latest update

Release 421a373 pushed and production deployment dpl_GyRNtdbmQanGo8J7QDnWmSRoVSzc READY with public aliases. Callback fix f492bad production deployment dpl_6K6BP6u648RjBofA1oyvUEMEqXV2 verified READY with wholesale-automation.vercel.app assigned. Production credentials approval requested in chat; prepared Vercel Secret RETELL_SMS_API_KEY, Production only, value EMPTY. Do not save until answered. Bundle approval covers API key, production webhook signing alignment, scheduler bearer in production Vault; no bypass needed.

Retell documented Get Chat omits phone fields. Updated callback resolver to use exact saved chat ID when telephone fields are absent, rejecting conflicting lead/phone metadata. 143 targeted tests pass. Native callback delivery remains unverified.

# Production SMS release checkpoint — 2026-10-15

Branch: `codex/retell-sms-production`, isolated from production commit `5c138f1`.
Checkout: `work/wholesale-sms-production` beside `work/wholesale-launch-prep`.

## Completed
- Production SMS_LIVE_ENABLED set false and redeployed: dpl_6dchgdYjKXBu4LhuLaeKfYdyfoLZ READY, production aliases assigned; code remains 5c138f1 until this SMS release is deployed.
- Ported consented-form queue, authenticated worker, CRM chat receipts, reply/STOP follow-up and SMS history only. No collector or general campaign activation.
- 143 targeted Python tests pass; frontend production build passes.
- Applied retell_form_sms_production to production Supabase dvzhzlipbwzzcliujzyz. Queue empty, scheduler enabled=false, cron inactive, tick requested=false.
- Production migration preserves private schema permissions and shared seller-outreach locks/call+SMS limits; does not overwrite claim_twilio_sms with older rehearsal behavior.
- Transactional SQL rollback verification passed: carrier reply, duplicates, phone-wide STOP, late reply, START and completed-task preservation. No messages sent.
- Fixed pinned numeric Retell agent version serialization, including V0, with tests.

## Remaining before owner test
1. Deploy this isolated code with production environment; do not promote full launch-prep branch.
2. Connect production Retell SMS credential and scheduler bearer securely. Prior credential approvals were rehearsal-only; production browser credential access/storage requires specific approval. Production scheduler needs no Vercel bypass.
3. Publish a production Retell agent version with production callback; preserve rehearsal V0. Verify signing/authenticated worker with no-send probes.
4. Verify exact public intake endpoints for hilltophome.co and thejaysdallas.com/sell. Sending remains OFF.
5. Confirm Retell actual chat callback phone schema and TwiML redirect compatibility before enabling replies. Existing redirect is experimental OFF; do not claim native provider acceptance.
6. User prefers to enter their number in actual forms, not in chat. Identify their explicit test submission before finite recipient allowlist. Never infer owner from latest lead. Test both forms separately; shared 24h cooldown and prior accepted-chat guard require a bounded test procedure, not global bypass. Do not clear DNC for a second test.
7. Perform controlled delivery/reply/STOP acceptance only after checks. SMS dispatch due at 60 seconds, scheduler 10-second cadence plus provider delivery latency. Keep calls off; no general sending.

Original bulk progress remains in wholesale-launch-prep/docs/START-HERE-NEXT-CHAT.md. Cumulative PropStream cap $50 unchanged.

## Live no-send checks
Production /api/health returned200; /api/forms/hilltop-home-co returned200 active=true. Unauthenticated worker probe returned503 because production scheduler authentication is not configured yet (closed, not a successful connection test). Hilltop public client posts to /api/get-offer; its server-side destination still requires verification. Jays sell page loads, server submission destination not yet established. Do not equate public availability with end-to-end submission evidence.

## Controlled owner acceptance procedure
Keep all sends off until configuration and signed callback checks pass. Have owner identify their own website submission, then set a finite allowlist to that exact phone. Do not guess from recency. Prepare each site separately; currently a prior accepted chat and 24-hour contact cooldown prevent testing the same phone twice immediately. Build an explicit owner-test exception scoped to submission ID and expiring authorization if needed; do not globally disable suppression/cooldowns or erase consent history. Verify first receipt, due+60sec handoff, provider receipt, handset arrival, reply task and STOP suppression; turn switches off again. Carrier latency is measured, not guaranteed exactly60seconds.
