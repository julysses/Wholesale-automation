# Controlled live acceptance — October 20, 2026

The owner now authorizes controlled live testing of Facebook Instant Forms and website forms using fresh test leads, including message delivery. This supersedes the live-test approval gate in RELEASED-PAUSED.md. Schedules must remain paused until the owner reviews the results.

## Verified before testing

- Production deployment remains READY: `dpl_Dwjn7sjLUB5C9X2JsoezbSKjJ6go` (release `a89815126d9a98ced016167d8e383641d133135f`).
- Vercel cron metadata remains disabled (disabledAt later than enabledAt); automatic custom-domain assignment remains false.
- Both private Retell scheduler flags are false; both Retell cron jobs are inactive.
- One pre-existing Retell session has status `review`. Do not reuse, recover, replay, or reconcile it.
- No live submissions, provider activity, sending-flag changes, or migrations were performed during this preflight.

## Pending input

Asked the owner for controlled phone numbers and an email inbox, plus availability to confirm handset receipt and reply. Prefer a distinct fresh number for native Facebook, Hilltop website, and Jays seller inquiry. Check each supplied number for existing sessions, suppression, and outreach limits before submission. Never clear suppression or close historical sessions to make a test pass.

## Execution sequence after recipients are supplied

1. Verify Meta native form identity `1548364970390755`, current form disclosure, controlled recipients, notification destination, and fresh job scope. Use a real new Meta test submission; do not manufacture a provider event as live integration evidence.
2. Configure a finite exact-job test window (at most 30 minutes), explicit recipient allowlist, and bounded provider spending. Keep all schedules disabled and broad production acceptance disabled. Verify effective deployment configuration before submitting.
3. Run each source separately with new request IDs. Trace consent evidence, deduplication, lead ownership, follow-up task, notification, and inquiry-specific SMS job. Exclude confirmed QA records from business reporting through the existing supported mechanism.
4. Invoke only the exact fresh job/turn workers. Verify durable provider IDs, callbacks, delivered status, handset acknowledgment, fresh inbound reply and response. Stop on ambiguous sends; never replay them.
5. Verify STOP/DNC suppression using the controlled recipient; preserve that suppression afterward. Distinguish provider delivery receipts from handset confirmation.
6. Restore sending flags to paused, verify the effective deployment and all schedule pauses, and publish evidence/results before requesting any broader live rollout.

Status: awaiting controlled recipient details. Live acceptance has not run; ad-readiness remains unproven.
