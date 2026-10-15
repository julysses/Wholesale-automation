## Provider support submitted — October15,2026

User explicitly approved sending the prepared investigation to Twilio and Retell. Both submissions verified in authenticated portals:
- Twilio ticket29953072, P2 Degraded, New, https://help.twilio.com/tickets/29953072 . Submitted3:44pmCentral. Includes failed messageSID, Retellchat/agent/version, verified serviceSID, prior delivered example, START/fresh form consent timeline, paused state and request for filtering/routing/delivery-callback investigation.
- Retell ticket65825, Open, https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825 . User completed email-code login. Portal confirmed request received; references Twilio ticket29953072.
No credentials or recipient phone/address included in submitted text. No paid support upgrade, retries or sends. Scheduler remains paused per previous verified state; no activation changes this turn. Await provider response before concluding cause or resuming. Submission proof screenshots in chat outputs/twilio-support-29953072.png and retell-support-65825.png. Existing authorization covers these support investigations; do not ask again just to continue them.

## DELIVERY BLOCKED — scheduler PAUSED October15,2026

Twilio Console confirms owner test SM0ad8ce793ccef33ea439760c1de917e0 UNDELIVERED error30007, created20:33:32UTC. Retell accepted/generated message, but carrier delivery failed. UCS2,5segments,$0.0415 listed. Message had no Messaging Service SID. Earlier Oct7 delivered message SM86c2dfa57821f764b97254659f925191 used MGaf5837f7a7cad183e8b38b1147728562. Do not assume missing serviceSID caused30007. Sender belongs to verified A2P Low Volume Mixed service; current campaign expressly covers opted-in property inquiry updates and registered sample begins 'Thanks for requesting an offer.' Failed text used longer investor pitch.

Paused private.retell_sms_scheduler.enabled and cron active=false. Application env sending flags stilltrue, so do not manually invoke worker. Owner job changed review; sms_events updated undelivered with carrier30007 and confirmed SID. No retry. Carrier failure and campaign/route review remain blockers; do not claim live delivery works. User confirmed nonreceipt after3:33 send. START reconciliation remains valid, history preserved. Need campaign-aligned first acknowledgement and verify Retell sending route/callback delivery integration, then explicitly controlled test. If provider investigation needed, obtain user authorization before contacting support. See docs/retell-carrier-support-draft.md (NOT SENT).

## Re-subscription reconciled; delivery investigation ongoing — October15, 3:33pm Central

Verified owner START event8275990d-ca46-5f67-8082-cf577036ce00 at20:26:33UTC, followed by fresh Jays consented form a7b6f49b-f460-4619-a22d-8afe776336d8 at20:28:22UTC. Added audited sms_resubscription_reviews with operator-only writes and helper requiring matching Twilio START after STOP and matching fresh form disclosure. Original STOP/DNC history preserved; manual lead DNC and later STOP still block. Applied reviewed_sms_resubscription and preserve_unclassified_dnc migrations. Rollback QA passed unreviewed START blocked, invalid START blocked, valid review allowed, laterSTOP/manualDNC blocked, claim success and access restrictions.69 targeted Python tests passed.

Recorded review for confirmed owner historicalSTOP and recovered latest unattempted form within its original15-minute deadline. Job e2e9231a-27ae-566f-8e3d-30c6096e5013 processed by scheduler20:33:29UTC; worker200 processed1/sendingtrue. Retell accepted chat_3e830c21a691319298d4d773598, publishedV1, generated personalized welcome at15:33:31CT. User explicitly still reports no delivery. NO RETRY: accepted is not delivered. Inspect Twilio message logs (Chrome tab1348648971), Retell chat tab1348648871. Calls and native AI reply forwarding still off. No provider delivery callback in CRM yet. Need carrier outcome and fix delivery failure before another test.

## Live test diagnosis — October 15, 2026, 3:17 p.m. Central

User reported Hilltop submission without SMS. Production has no recent Hilltop receipt (latest October9 Central); one new Jays seller receipt at20:17:31UTC, submission557529d4-8225-4428-88a8-0791935a046f, lead50bc5279-2a96-4176-a6b4-adc364313387. Consent accepted and rendered disclosure matches. Intake notification seller_sms=consent_or_suppression_hold; owner_email=accepted. No Retell job/provider attempt created. Phone ending0280 matches durable Twilio STOP opt-out dated October6 Central (October7 03:30UTC), registrya412d09e-fe46-513b-b2d8-bfc8f252f259. intake_phone_status suppressed=true; current lead dnc=false does not override phone-wide registry.

Asked user to confirm whether3:17p.m./ending0280 is their test because reportedHilltop differs from storedJays source. Do not assume identity or remove DNC. Twilio START can re-subscribe carrier side; current CRM deliberately retains STOP until reviewed, so START alone is not sufficient to promise app delivery. Need confirm test identity, observe new opt-in and reconcile suppression explicitly before any fresh test. No sending configuration changed. Production scheduler remains enabled; empty queue is expected for suppressed inquiry.

## LIVE production SMS — October 15, 2026

Owner explicitly requested live activation without recipient restriction. Production code b94d086 deployed READY as dpl_F1jXupfYoa6HUx6C27SwzYg5e8nY; wholesale-automation.vercel.app alias assigned. Saved production RETELL_FORM_SMS_ENABLED=true, RETELL_SMS_LIVE_ENABLED=true, SMS_LIVE_ENABLED=true, RETELL_SMS_LAUNCH_APPROVED=true and RETELL_SMS_ALL_CONSENTED_FORMS=true. No acceptance-verification claim: real handset evidence pending owner test.

Production Supabase scheduler enabled=true and cron wholesaleos-retell-form-sms active=true, every10seconds. Tick verified idle/requestedfalse with zerojobs. Authenticated production worker request6 returned200 processed0/sending_enabled=true. Read-only request5 returned200 connectedtrue with agent/version/published/callback checks alltrue. Calls, nurture and experimental AI reply forwarding remainOFF (production flags absent/defaultfalse). Replies/STOP go through existing Twilio production CRM handler. No county collection, PropStream spend or cold-lead campaign activated; $50 cap preserved.

Final backend705 passed; targetedSMS/form102 passed; frontend140 passed, production build passed, lint no new findings. Earlier production rollback SQL verified queue timing/claims/sharedledger/expiry/DNC and carrier reply/duplicate/STOP/START/followup. No actual SMS sent during QA. Owner will test Hilltop https://hilltophome.co/get-an-offer and Jays https://thejaysdallas.com/sell with SMS consent. Expect due+60seconds plus up to10seconds scheduler and carrier delay, within9am–7pm Central.15-minute expiry means after-hours forms may expire without automatic SMS. Prior accepted-chat guard and24h shared cooldown block second initial SMS to samephone across forms. Do not clear DNC or ledger to force test. Actual delivery, real reply and STOP acceptance still need observation. Do not ask for an owner-phone allowlist again.

Emergency stop: deactivate cron and private.retell_sms_scheduler.enabled; disable production RETELL_SMS_LIVE_ENABLED and redeploy. Never replay uncertain/review or expired jobs without reconciliation.

## Current launch decision — October 15, 2026

User explicitly said "do not restrict. Make it live and I will test when it is live". Supersedes historical owner-only test instructions below. Added RETELL_SMS_LAUNCH_APPROVED and RETELL_SMS_ALL_CONSENTED_FORMS, retaining consent, DNC, phone match, expiry, contact hours and shared duplicate limits. Production settings saved; deployment and scheduler activation in progress. 102 targeted tests pass. Calls, nurture and experimental AI reply forwarding remain OFF by absent production flags/default false. No handset delivery claimed. See docs/retell-live-qa.md. Do not request owner-phone identification again.

## Additional QA findings

Frontend production build passed; lint regression gate passed (149 existing findings, zero new). Live unsigned Retell and Twilio callbacks both rejected401. Production rollback tests repeated successfully for carrier replies, duplicates, phone-wide STOP, late replies and task preservation. Fixed missing wrong-number classification to match the agent prompt: those replies now suppress and never forward to Retell.62 targeted SMS tests pass. Pinned-release probe deployment ad2a6b1 was queued; superseding with this fix. Live handset test still awaits owner-identified form submission; no messages sent.

## Live-test QA in progress — October15,2026

User requested all QA and live testing. Full backend suite692 passed; frontend140 passed. Strengthened read-only production probe to verify configured agent ID, pinned version, published=true and exact production callback.23 targeted probe/worker tests pass (includes3 new negative cases). No sending enabled.

Added tests/sql/retell_form_sms_production_qa.sql and executed against production in a rolled-back transaction: no early claim, one due claim, no duplicate claim, shared Retell/Twilio limits, expiry, DNC and restricted queue access passed. Initial fixture omitted required city; corrected fixture and reran successfully. No test records persisted.

Owner test identification requested: submit Hilltop form with their own mobile and SMS consent, then identify name/time. No answer yet; do not guess owner from recent leads or use historical allowlist. Pending real carrier delivery/reply/STOP test cannot be replaced by unit tests. Native Retell redirect still unverified/OFF. Retell UI shows chat_started, chat_ended, transcript_updated and chat_analyzed selected on draft inherited from V1.

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
