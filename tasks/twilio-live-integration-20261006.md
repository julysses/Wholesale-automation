# Twilio integration — October 6, 2026

## Scope and safety
Existing sender +14698049920 and service MGaf5837f7a7cad183e8b38b1147728562. Campaign is in progress, not approved. SMS_LIVE_ENABLED remains false. No seller messages, account purchases or credential rotation authorized by this change.

## Implementation
- Native /webhooks/twilio/inbound and /status verify SDK signatures against configured HTTPS public URL, account SID and message identity; reject invalid requests before writes.
- record_twilio_event is server-only SECURITY INVOKER RPC. Transactionally persists deduplicated events, STOP suppression for every matching lead (including future imports via registry), pauses follow-up, and alerts operators. START never silently clears DNC. Event history preserves late/out-of-order delivery events.
- Outbound client fails closed without credentials/live gate. Requires matching server consent receipt and suppression clearance. Claims a durable outbound record before provider request, persists SID, supplies service SID and signed status callback URL, and never replays an existing attempt.
- Migration created with Supabase CLI and applied explicitly; no historical replay. Rollback SQL test confirmed duplicate receipt idempotence and unknown-phone STOP. anon/authenticated denied RPC, service_role allowed.
- 316 backend tests passed, including callback signature/account/missing-secret/storage failure and outbound claim/consent/suppression cases.

## Execution status
Code, CI, production secrets, callback routing, Advanced Opt-Out and synthetic callback acceptance completed below. Actual handset/carrier delivery and STOP acceptance remain open.

## Live configuration and acceptance
- PR #19 merged at 0913e095. Production cold-start verification exposed a missing Twilio dependency in the separate api/requirements.txt; repaired immediately in 3f96bbd, with lazy SDK import and a regression check. Backend/public intake health returned 200. Latest release checks passed. Do not describe the initial 503 deployment as successful.
- Vercel production secrets saved: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_MESSAGING_SERVICE_SID, TWILIO_WEBHOOK_BASE_URL; SMS_LIVE_ENABLED=false. Existing SMS_PROVIDER explicitly set to twilio (production/preview). No credentials committed or printed. The production config values target the existing approved account and number; no credential rotation or number purchase.
- Twilio service saved: incoming HTTP POST https://wholesale-automation.vercel.app/webhooks/twilio/inbound; delivery status https://wholesale-automation.vercel.app/webhooks/twilio/status. Advanced Opt-Out enabled. STOP/HELP/START response messages now identify Hilltop and its support number; START directs manual resumption and does not clear CRM DNC.
- Public signed synthetic inbound/status requests each returned 200 twice; invalid signatures each returned 401. Database shows exactly one event per fixture. These are synthetic callback tests (raw_payload.ValidationTest=controlled-synthetic-oct06), NOT evidence of an actual carrier message or delivery. No SMS was sent by these requests.
- Rollback SQL assertions verified STOP sets DNC/pauses sequences and calls; START preserves suppression. All temporary SQL changes rolled back. The two synthetic signed callback records remain clearly labeled for evidence; their recipient was Julio's authorized test phone.
- Fresh website-to-CRM test returned 200 and processed receipt 94a71914-7a4b-4055-8e77-c60e31956c92 linked to synthetic lead 08917e25-4555-4e1a-a15f-c7cc20527001 with SMS declined. Archived fixture as dead, calls paused, sequences off and task done.
- Security advisor did not flag the new RPC; it continues to report existing mutable-search-path/security-definer findings on other functions. These pre-existing findings are outside this Twilio patch and remain general launch audit work. Reference: https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable

## Outstanding live gates / resume here
1. User was asked to text HELP then STOP from (214) 701-0100 to (469) 804-9920. Await actual inbound callback rows, Twilio logs and user confirmation of replies. Do not count synthetic callbacks as this test.
2. Campaign CM81b71bfdf3483a566e6ecf0161c840b9 still requires carrier approval. Keep SMS_LIVE_ENABLED=false until approval and a controlled delivery test can be completed. No SMS blast or real seller outreach authorized by this test.
3. After approval, run positive-consent controlled sender test only to Julio, reconcile provider Message SID/status callback, then verify STOP prevents another send. Julio's test phone may remain DNC after real STOP; only clear a test suppression after explicit renewed consent and identifying the test records.
4. Internal owner alerts and buyer-list marketing remain excluded from the seller inquiry campaign. Other providers (email, AI calls, Meta) are not completed by this integration.

User-facing proofs in outputs: twilio-production-secrets.jpg, twilio-callbacks-configured.jpg, twilio-opt-out-configured.jpg. The Vercel token is write-only and no longer retained in browser automation variables. Temporary signed fixture file deleted after validation.

## No-response investigation
- User reported no reply to HELP/STOP. Twilio Programmable Messaging Logs showed no logs for this account, and CRM had no real inbound test events. This does not establish an A2P rejection or callback failure; no provider event is available to diagnose yet.
- Number +14698049920 is active in US1 and assigned to the correct Messaging Service. Number UI explicitly confirms service configuration handles inbound messages. Service reload confirmed POST inbound URL and delivery callback persist.
- Replaced the dormant number-level demo SMS URL with the same CRM inbound endpoint and verified saved value. This removes obsolete routing but is not evidence of the root cause, since service routing already overrides it. Voice settings unchanged.
- Latest bf5db0a deployment succeeded on Vercel and all three Railway services; production /api/health returned 200. Campaign remains In progress.
- Asked user to send a fresh plain SMS HELP to full +1 (469) 804-9920 and report timestamp and handset delivery status. Resume by refreshing Twilio logs and correlating any Message SID with CRM receipt. If no Twilio receipt after a confirmed SMS send, investigate carrier/number provisioning with Twilio using the test timestamp. No external support message sent.

## Second HELP test — October 6, 3:44 PM Central
- Read the existing Google Voice conversation for +14698049920: outgoing HELP displayed October 6 at 3:44 PM Central. Google Voice calling identity is +12147010100. No received response or explicit delivery receipt was visible. Do not treat the sent bubble as carrier delivery confirmation.
- Refreshed Twilio Messaging Logs: no logs for the account. Error logs for the last 24 hours: No events found. Number Properties confirms Voice, SMS, MMS, SIP capabilities, local Dallas number.
- Evidence points to non-arrival before the CRM webhook, but sender-provider versus Twilio ingress cause remains unproven. Campaign approval is a separate outbound gate, not a proven explanation for absent incoming logs.
- Next: obtain Twilio inbound-routing trace for the timestamp, or compare a test from a cellular carrier rather than Google Voice. Support message drafted below; NOT sent. User authorization required to contact external support.

### Draft Twilio support request
Subject: Incoming SMS to +14698049920 absent from message logs

Please investigate inbound SMS routing/provisioning for our existing number +14698049920, SID PNb952c10eb0350422ccd08b1d8c5ce738, the signed-in Twilio account (account SID omitted from Git).

A controlled HELP text was sent from Google Voice +12147010100 on October 6, 2026 at 3:44 PM America/Chicago (20:44 UTC). It appears in the sender conversation, but no reply was received and our Twilio Programmable Messaging Logs show no records. The last-24-hour Error Logs show no events. Please trace ingress from the sending provider and confirm SMS provisioning/routing for this destination; no Message SID exists in our console to supply.

The number lists SMS/MMS capabilities and active US1 message routing. It belongs to Messaging Service MGaf5837f7a7cad183e8b38b1147728562, with Advanced Opt-Out enabled and inbound HTTP POST to https://wholesale-automation.vercel.app/webhooks/twilio/inbound. Number-level webhook matches. Controlled signed synthetic requests to the endpoint previously succeeded; these were not real carrier messages.

A2P campaign CM81b71bfdf3483a566e6ecf0161c840b9 is under review. Application outbound SMS remains disabled. Please determine the cause of missing inbound receipt independently of outbound campaign approval. Do not purchase, replace, release or port the number.

## Payment restoration and real inbound success
- User reported account suspension for nonpayment and restored payment. After restoration, Twilio received real HELP at 2026-10-06 15:51:29 America/Chicago (20:51:29 UTC), Message SID SMb3f2b5ca15cfccf7905a3d69e856cf28. Twilio shows Incoming, HELP, from authorized test number to existing sender, cost $0.0083.
- CRM sms_events contains matching real Message SID, direction inbound, status replied, body HELP, OptOutType HELP, opt_out false. The status replied is the CRM inbound classification, NOT proof of an outbound automatic reply. This confirms carrier ingress through the signed CRM callback and persistence.
- Twilio detail UI says no HTTP Requests logged for this event, despite the matching persisted receipt. Do not claim Request Inspector HTTP evidence.
- Google Voice conversation still showed only the two sent HELP messages when checked. Automatic HELP reply delivery is not verified. Asked user to send STOP now and report replies; verify real STOP record and dnc_registry before marking opt-out acceptance complete.
- Earlier missing-ingress support draft is superseded by restored real delivery and has NOT been sent. No support escalation needed for the now-resolved absence of incoming messages. Outbound campaign approval and delivery acceptance remain separate open gates; sending stays disabled.
