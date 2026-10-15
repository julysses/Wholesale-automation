## Latest update

Release 421a373 pushed; production deployment dpl_GyRNtdbmQanGo8J7QDnWmSRoVSzc initiated (verify READY and aliases). Production credentials approval requested in chat; prepared Vercel Secret RETELL_SMS_API_KEY, Production only, value EMPTY. Do not save until answered. Bundle approval covers API key, production webhook signing alignment, scheduler bearer in production Vault; no bypass needed.

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
