# WholesaleOS SMS repair and acceptance plan

Updated October 16, 2026, evening Central. Sending and recurring collection remain paused.

## What is now confirmed

- Twilio support ticket [29953072](https://help.twilio.com/tickets/29953072), October 16 at 6:14 PM Central: the internal team reports remediation of the undelivered-message issue and asks for a retest. Status is Pending. Delivery has not been retested.
- Retell support ticket [65825](https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825): Retell's BYO Twilio SMS implementation supplies body/from/to, but no MessagingServiceSid or statusCallback. Retell currently offers no setting to supply that service ID.
- Live Twilio configuration: the sender ending 9920 already belongs to the registered Low Volume Mixed Messaging Service, its campaign is Verified, and both inbound and status callback URLs point to WholesaleOS. Retell's sender-pool workaround is already satisfied.
- A missing service ID in the message log does not prove failed A2P attribution. Twilio documents that outbound logs omit that field when the API request omits it, even for a number in the sender pool. [Twilio service troubleshooting](https://www.twilio.com/docs/messaging/tutorials/send-messages-with-messaging-services).
- The service's delivery callback is not used when the request omits the service ID. This explains a reporting gap, separately from carrier filtering. [Twilio callback guidance](https://help.twilio.com/articles/41980369432859).

## Completed test-control repair

Added an authenticated POST endpoint that processes only the explicitly selected fresh job. It cannot fall back to draining other queued work. Expiry, suppression, consent, prior-contact holds, contact hours and duplicate-send protections remain enforced. Its database migration is installed and production rollback acceptance passed without changing existing job or SMS records. No actual provider request was made by these tests.

Code commit: 974a46203313b97e7a1d5494dc6eff20c9bca98a. Local validation: 864 backend tests plus six subtests, 142 pipeline tests. Check the current launch status for deployment verification.

## Controlled retest — authorized; publication and preparation complete, send pending

1. Dashboard sign-in and published V1 inspection are complete. Published V2 has the reviewed prompt and welcome; both survived reload and the production connection probe passed. See docs/retell-v2-controlled-retest.md for exact text and test scope.
2. The 136-character acknowledgment is published as V2: “Hilltop Home Co. (The Jays Dallas, LLC): Thanks for your property inquiry. Julio will follow up. Reply STOP to opt out or HELP for help.” V2 is now published and pinned; only the delivery test remains pending.
3. The concrete owner-only test is approved, including the reviewed agent version and message; do not request this approval again. A fresh consented inquiry must use the confirmed owner phone ending 0280. No customer or county lead is a test recipient.
4. The approved old, provider-confirmed failed test hold has been stopped with its undelivered status, SID, error 30007, original consent and STOP history preserved. Do not repeat that reconciliation or replay it. Leave the uncertain accepted job ending 0100 and unrelated expired job ending 9307 untouched.
5. Verify the new submission, lead, assigned follow-up, matching consent, phone eligibility and finite due/expiry window. Run only its exact new job ID during configured contact hours. The scheduler remains disabled. Stop if another hold or uncertainty appears; do not bypass it.
6. Confirm the new carrier Message SID/status in Twilio and actual handset receipt. Record evidence separately from Retell API acceptance. A fresh test or a failure does not authorize automatic retries.
7. Verify inbound reply and STOP handling under a specifically approved bounded conversation test. Both website paths still need acceptance evidence. Do not close the launch gate merely because a test text arrives.

## Delivery reporting decision before general activation

Native Retell currently cannot request the application's per-message Twilio callback. Keeping the sender in the pool does not repair that behavior. Do not claim automatic CRM delivery reconciliation is operational.

Preferred engineering path if Retell cannot provide supported receipts: keep Retell for conversation generation via its API chat interface and send through WholesaleOS's existing Twilio client, which already supplies the Messaging Service and a callback bound to the durable message ID. The generation adapter, durable ownership/turn SQL and exact-turn generation worker are implemented and tested locally. The new migration is not applied; Twilio dispatch, webhook/monitor wiring, deployment and live acceptance remain. Nothing is activated. See docs/retell-api-twilio-transport.md for the exact implementation checkpoint. [Retell API chat](https://docs.retellai.com/api-references/create-chat), [Retell chat completion](https://docs.retellai.com/api-references/create-chat-completion), [Twilio delivery tracking](https://www.twilio.com/docs/messaging/guides/track-outbound-message-status).

Implementation must preserve one durable claim per turn; serialize inbound turns; prevent duplicate native Retell and app sends; retain actual user text without fabricated user turns; handle model/tool output separately from messages; recheck consent and suppression immediately before dispatch; hold all uncertain provider outcomes without retry; and bind carrier callbacks to the exact claim. Generated text is not a delivery receipt. STOP and other control messages must stay local and must never generate an AI reply. Confirm a finite Twilio queue validity period; the existing service default is ten hours and only bounds Twilio's queue, not downstream carrier latency.

A narrower read-only reconciliation option is acceptable only if supported provider evidence identifies the exact Twilio message. Do not automatically bind messages using only phone number and timestamp, and do not alter historical outcomes based on assumptions.

## Separate onboarding gate

The approved 34-record county index test is complete. Full-notice OCR text upload remains pending the earlier specific approval described in WholesaleOS-Notice-Evidence-Upload.md. No collection, tracing, upload or outreach is authorized by this SMS plan. PropStream and the cumulative $50 tracing cap remain unchanged.
