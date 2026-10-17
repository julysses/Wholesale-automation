# Automatic app-owned SMS processing

## Implemented behavior

Website intake persists its consent and assigned lead/task, then creates an immutable app-owned acknowledgment when the app transport is explicitly selected. The automatic worker takes one queue selection and invokes exactly one existing acknowledgment, generation or reply worker. Replies have priority over generation, then acknowledgments; selected but unclaimed work has a 90-second selection lease so an ineligible row cannot monopolize the queue. Status transitions clear turn selection leases. Each provider operation still requires its own one-shot SQL claim and current consent, suppression, ownership, expiry and contact-window checks.

The private database scheduler runs at ten-second intervals only after explicitly activated. It serializes HTTP requests, reads the existing retell_sms_worker_bearer Vault secret, and calls only POST /webhooks/_worker/retell-app/automatic. It refuses a simultaneously enabled native scheduler. HTTP failure, timeout, absent completion after 90 seconds, or an unexpected/disabled application response pauses the scheduler and surfaces a launch-monitor finding. It does not replay ambiguous provider work. Missing credentials and native scheduler conflicts are also operator findings. Scheduler hours default to 9 AM–7 PM America/Chicago and must match application hours when activated.

Installation leaves private.retell_app_scheduler.enabled=false and cron job wholesaleos-retell-app-sms inactive. Browser roles cannot select scheduler configuration or invoke worker-selection functions; the service role can select monitoring data but cannot update scheduler controls or invoke its HTTP tick.

## Application gates

Existing SMS, form SMS, Retell live, app transport, Twilio service/callback, pinned agent/version, recipient eligibility and contact-hour checks still apply. RETELL_APP_AUTOMATION_ENABLED defaults off.

For a bounded owner test, explicitly set RETELL_APP_TEST_APPROVED, the allowlisted owner phone, RETELL_APP_AUTOMATION_TEST_JOB_ID, RETELL_APP_AUTOMATION_TEST_STARTED_AT and RETELL_APP_AUTOMATION_TEST_EXPIRES_AT. The timestamp range must be currently valid, timezone-aware, and at most 30 minutes. This selects only the exact job and its first actual carrier turn: at most one initial acknowledgment, one session creation/completion and one conversational reply. An invalid, expired or blank test target disables processing even if general acceptance is enabled. These are test dispatch bounds, not a promise that a carrier cannot deliver later.

For general production processing, remove the test-target settings only after explicit launch authorization and verified acceptance. RETELL_APP_ACCEPTANCE_VERIFIED is required. Retain an explicit phone allowlist, or deliberately enable RETELL_APP_ALL_CONSENTED_FORMS after end-to-end acceptance. This does not permit cold county outreach or bypass consent/STOP checks.

## Deployment and acceptance sequence

1. Run full backend, pipeline and real PostgreSQL concurrency tests; push and verify exact-commit CI.
2. Apply only the automatic-queue migration. Verify inactive cron/configuration, server-only privileges, function bodies, unchanged preexisting jobs/SMS and no app work created.
3. Deploy the exact tested commit with sending/automation OFF. Verify health and unauthorized requests, then a Vault-authenticated automatic POST returns disabled without selecting work. Confirm a disabled SQL tick makes no HTTP request.
4. Obtain a separate bounded owner-only app-transport acceptance authorization. The earlier native Retell one-message approval does not authorize switching that test to the new app transport or enabling recurring automation. Do not silently broaden it.
5. During 9 AM–7 PM Central, confirm fresh owner consent; prove actual inquiry/assignment/history, exact carrier callback and handset delivery, one real reply and STOP suppression. Validate both website paths and duplicate intake/callback behavior. Keep a prewritten pause cleanup and preserve every uncertain receipt without retry.
6. Restore all sending/automation gates and cron to paused after the approved test. Document provider/handset receipts and actual spend, then separately decide on general activation.

## Limits still requiring live evidence

Local tests and a healthy deployment do not prove carrier delivery, the reviewed Retell prompt's response to a real inquiry, live reply/STOP history, or an observed county ingestion cycle. Full-notice OCR transfer still awaits specific approval after earlier automatic review rejected that transfer. Collection stays paused; retain PropStream and the cumulative $50 trace cap.
