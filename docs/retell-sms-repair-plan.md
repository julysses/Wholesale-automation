## Recovery and monitoring completed locally — October 16, 2026, evening Central

Recovery endpoints reconcile one exact app acknowledgment or carrier reply while sending is paused. Known saved carrier acceptance repairs the parent; stale uncertain creation/completion/dispatch is held without requeue or resend. Receipt bodies, SIDs and delivery statuses are preserved. Fresh dispatch ages from its own SMS ledger timestamp rather than an earlier generation claim. Expired unprocessed replies stop; generated-but-unsent replies hold the conversation. The existing owner monitor now includes stalled API sessions/turns and app acknowledgments.

A late acknowledgment failure now holds a pending session. Generation rechecks current conversation and acknowledgment state before provider operations. The two earlier UNAPPLIED transport migrations were amended for this guard. New migration **20261017015318_retell_app_recovery_monitoring.sql** adds recovery and monitoring. All three remain prepared, not applied at this checkpoint; exact files/hashes are in **docs/retell-app-release-manifest.json**.

Validation: **1,041 pytest tests plus six subtests; 174 pipeline tests; real PostgreSQL contention passed**. Eight carrier reconciliations raced eight recoveries without losing delivery; eight stale-generation recoveries produced one review hold. Zero provider calls. Logs: **work/retell-api-transport/recovery-pytest-all.log**, **recovery-pipeline-all.log**, **recovery-postgres-concurrency.log**. The initial synthetic monitor fixture omitted the call lead_id column; fixed before passing verification. Monitor tests now load the current incident reopening implementation.

Production prerequisite reads: project dvzhzlipbwzzcliujzyz has no new API session/turn tables or delivery_transport column. Existing monitor body matches local prior migration after whitespace normalization (MD5 de8623a582f7edc40234f3b62fe55943). Three existing form jobs fingerprint ce3393269d0d68a2d42ccd33d70f74be; 12 SMS ledger rows fingerprint645e09a4b946be7cab46d96e48d97faa. Browser refresh confirmed production RETELL_SMS_LIVE_ENABLED=false and no RETELL_APP_ variables. No environment setting was changed. Existing retention and monitoring cron jobs remain untouched.

Next: exact-commit CI, apply only the three reviewed SMS migrations in order, verify old job/SMS fingerprints and server-only privileges, deploy this code to the existing production Vercel project with sending OFF, and verify paused/authenticated endpoints. No scheduler activation or new owner SMS is authorized by deployment. New app-transport acceptance remains distinct from the approved native one-message owner test. Full-notice OCR transfer approval remains pending. Goal active, incomplete.

## Inquiry/reply wiring and transcript separation verified locally — October 16, 2026, 8:50 PM Central

Latest user-supplied Retell support screenshots confirm native BYO sends omit MessagingServiceSid and statusCallback; Retell recommends keeping the number in the registered sender pool. This is evidence of the integration limitation, not proof that it caused carrier error 30007. Keep Retell for conversation generation and Twilio for carrier delivery. No support reply was sent.

Implemented inquiry route selection with an explicit app-specific gate, immutable fixed acknowledgment/sender, no fallback on invalid configuration, and truthful existing-job reporting after a route switch. Native workers cannot activate in app mode, process app claims, or age app jobs into review. The native stale-update query now requires the pending ownership migration: apply it before deploying this code or running the native owner retest on this build.

Signed Twilio inbound handling commits carrier evidence/suppression/human follow-up first, then queues the exact carrier event for an unambiguous accepted app inquiry. Duplicates can repair a lost enqueue response without another turn. Unconfirmed persistence returns 503 and cannot fall through to native Retell. Mixed/ambiguous ownership is held. STOP/HELP/resubscription controls remain in the carrier/CRM handler. No generation or SMS occurs within the webhook.

Bearer-authenticated POST endpoints are implemented for one exact UUID each: /webhooks/_worker/retell-app/ack/{job_id}, /generate/{turn_id}, and /reply/{turn_id}. The last two share the same /webhooks/_worker/retell-app prefix. Gates are checked before database access; each underlying worker rechecks eligibility and wins its own durable claim. There is no batch drain, provider fallback, recurring trigger, or automatic generation-to-dispatch chain.

API-chat callbacks validate exact session/lead/agent/version/metadata and archive as generation-only webhook receipts. They do not duplicate Twilio SMS history, manufacture delivery status, create duplicate tasks, or suppress leads from generated transcripts. A create callback arriving before session binding is archive-only and cannot bind or resume an operation.

Validation: **1,033 full pytest tests plus six subtests passed**, 364 existing deprecation warnings. Log: **work/retell-api-transport/wiring-pytest-all.log**. Includes actual signed webhook retries, unauthorized/paused exact endpoints, transport isolation, route-switch deduplication, controls and generation-only callback history. Existing SQL is unchanged; prior 162 pipeline tests and eight-worker PostgreSQL contention results remain previous-checkpoint evidence, not newly rerun results.

Both **20261017012707_retell_app_transport_ownership.sql** and **20261017013643_retell_app_twilio_outbox.sql** remain unapplied. No production database/env change, deployment, provider generation, SMS or scheduled activation occurred. Last verified runtime remains974a462 / dpl_D8ws6MBB6E7uc7ARAuikZUEdm6wH; not refreshed this turn.

Next: implement stale-operation recovery/monitor findings without replay; verify exact-head CI and migration baseline; apply only reviewed pending SMS migrations; deploy with all sending gates OFF; validate paused/authenticated endpoints and receipt handling. Then prepare separately bounded app-transport acceptance for both websites, delivery, reply and STOP. The previously approved native owner retest must not be silently changed to this new transport. It still needs fresh consent and 9 AM–7 PM Central. Full-notice OCR upload remains pending separate authorization; prior automatic review rejected that transfer for missing specific approval. County collection and general SMS stay paused. Goal active and incomplete.

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

Preferred engineering path if Retell cannot provide supported receipts: keep Retell for conversation generation via its API chat interface and send through WholesaleOS's existing Twilio client, which already supplies the Messaging Service and a callback bound to the durable message ID. The generation adapter, durable ownership/turn SQL, generation worker, Twilio outbox/dispatcher and exact status-callback synchronization are implemented and tested locally. Both new migrations remain unapplied; inquiry/inbound routing, worker endpoints, monitoring, deployment and live acceptance remain. Nothing is activated. See docs/retell-api-twilio-transport.md for the exact implementation checkpoint. [Retell API chat](https://docs.retellai.com/api-references/create-chat), [Retell chat completion](https://docs.retellai.com/api-references/create-chat-completion), [Twilio delivery tracking](https://www.twilio.com/docs/messaging/guides/track-outbound-message-status).

Implementation must preserve one durable claim per turn; serialize inbound turns; prevent duplicate native Retell and app sends; retain actual user text without fabricated user turns; handle model/tool output separately from messages; recheck consent and suppression immediately before dispatch; hold all uncertain provider outcomes without retry; and bind carrier callbacks to the exact claim. Generated text is not a delivery receipt. STOP and other control messages must stay local and must never generate an AI reply. Confirm a finite Twilio queue validity period; the existing service default is ten hours and only bounds Twilio's queue, not downstream carrier latency.

A narrower read-only reconciliation option is acceptable only if supported provider evidence identifies the exact Twilio message. Do not automatically bind messages using only phone number and timestamp, and do not alter historical outcomes based on assumptions.

## Separate onboarding gate

The approved 34-record county index test is complete. Full-notice OCR text upload remains pending the earlier specific approval described in WholesaleOS-Notice-Evidence-Upload.md. No collection, tracing, upload or outreach is authorized by this SMS plan. PropStream and the cumulative $50 tracing cap remain unchanged.
