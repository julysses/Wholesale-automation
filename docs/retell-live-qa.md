# Production SMS acceptance — October 15, 2026

Scope: consented seller inquiries from Hilltop and Jays. Calls, nurture and county campaigns remain OFF. PropStream budget untouched.

| Check | Evidence | Result |
|---|---|---|
| Backend suite | 692 tests before final narrow QA fixes | Pass |
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
