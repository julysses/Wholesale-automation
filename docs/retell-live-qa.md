## LIVE production SMS — October 15, 2026

Owner explicitly requested live activation without recipient restriction. Production code b94d086 deployed READY as dpl_F1jXupfYoa6HUx6C27SwzYg5e8nY; wholesale-automation.vercel.app alias assigned. Saved production RETELL_FORM_SMS_ENABLED=true, RETELL_SMS_LIVE_ENABLED=true, SMS_LIVE_ENABLED=true, RETELL_SMS_LAUNCH_APPROVED=true and RETELL_SMS_ALL_CONSENTED_FORMS=true. No acceptance-verification claim: real handset evidence pending owner test.

Production Supabase scheduler enabled=true and cron wholesaleos-retell-form-sms active=true, every10seconds. Tick verified idle/requestedfalse with zerojobs. Authenticated production worker request6 returned200 processed0/sending_enabled=true. Read-only request5 returned200 connectedtrue with agent/version/published/callback checks alltrue. Calls, nurture and experimental AI reply forwarding remainOFF (production flags absent/defaultfalse). Replies/STOP go through existing Twilio production CRM handler. No county collection, PropStream spend or cold-lead campaign activated; $50 cap preserved.

Final backend705 passed; targetedSMS/form102 passed; frontend140 passed, production build passed, lint no new findings. Earlier production rollback SQL verified queue timing/claims/sharedledger/expiry/DNC and carrier reply/duplicate/STOP/START/followup. No actual SMS sent during QA. Owner will test Hilltop https://hilltophome.co/get-an-offer and Jays https://thejaysdallas.com/sell with SMS consent. Expect due+60seconds plus up to10seconds scheduler and carrier delay, within9am–7pm Central.15-minute expiry means after-hours forms may expire without automatic SMS. Prior accepted-chat guard and24h shared cooldown block second initial SMS to samephone across forms. Do not clear DNC or ledger to force test. Actual delivery, real reply and STOP acceptance still need observation. Do not ask for an owner-phone allowlist again.

Emergency stop: deactivate cron and private.retell_sms_scheduler.enabled; disable production RETELL_SMS_LIVE_ENABLED and redeploy. Never replay uncertain/review or expired jobs without reconciliation.

# Production SMS acceptance — October 15, 2026

Scope: consented seller inquiries from Hilltop and Jays. Calls, nurture and county campaigns remain OFF. PropStream budget untouched.

| Check | Evidence | Result |
|---|---|---|
| Backend suite | 705 tests on final live code | Pass |
| Frontend suite | 140 tests across 32 files | Pass |
| Final SMS changes | 102 targeted tests, including wrong-number suppression and pinned-release mismatch checks | Pass |
| Frontend production build | TypeScript and Vite build | Pass |
| Lint regression | No new findings;149 existing | Pass |
| Database queue | Transaction rolled back: due time, exactly one claim, shared Twilio/Retell ledger, expiry, DNC, access | Pass |
| Carrier CRM receipts | Transaction rolled back: reply, duplicate, phone-wide STOP, late reply, START, task preservation | Pass |
| Unsigned live callbacks | Retell401 and Twilio401 | Pass |
| Production credential | Vault-authenticated probe200; wrong bearer401; sendingfalse | Pass, prior deployment |
| Published release | New read-only check for agent/version/published/callback | Pass: live probe200; all four checks true |
| Both public routes | Hilltop upstream422 and Jays upstream email422 using non-contactable invalid data | Validation path passes; successful intake not yet proven |
| Website submission → CRM → handset | Owner will test after live activation | Pending |
| 60-second timing | Queue due+60seconds, tick10seconds; actual handset timing not measured | Pending |
| Real reply → CRM follow-up | Synthetic database tests only | Pending carrier acceptance |
| Real STOP → suppression | Synthetic database tests only | Pending carrier acceptance |
| Retell two-way handoff | Experimental redirect remains OFF | Unverified |

## Owner-approved live launch

Owner explicitly requested: "do not restrict. Make it live and I will test when it is live". This supersedes the owner-only test proposal. Enable new consented seller-form SMS for all eligible recipients; calls, nurture campaigns and experimental AI reply forwarding remain off. Launch approval is separate from carrier acceptance so no unperformed handset test is marked verified.

1. Deploy production with RETELL_FORM_SMS_ENABLED, RETELL_SMS_LIVE_ENABLED, SMS_LIVE_ENABLED, RETELL_SMS_LAUNCH_APPROVED and RETELL_SMS_ALL_CONSENTED_FORMS=true.
2. Enable existing production cloud scheduler after deployment is READY. Verify authenticated worker and pinned published agent probe.
3. Owner tests Hilltop /get-an-offer and Jays /sell using SMS consent checkbox. Record actual receipt, provider acceptance and handset delivery separately.
4. Replies create CRM follow-up; STOP suppresses matching phone records. Actual carrier reply/STOP evidence remains pending owner testing. Experimental Retell reply forwarding stays off.
5. Shared 24-hour cooldown and prior accepted-chat guard prevent repeat initial texts to the same phone, including a second form. Never clear DNC/ledger to force another text.
6. Contact-hour checks and 15-minute expiry remain enforced. Due time is 60 seconds; 10-second scheduler and carrier delay mean handset delivery is not an exact 60-second guarantee.
