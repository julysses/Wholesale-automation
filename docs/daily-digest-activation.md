# Owner digest activation and acceptance

Implementation is in the draft launch branch. Rehearsal migration only; production remains unchanged.

## Delivery contract

The authenticated GET /webhooks/_worker/daily-lists scans sources, then attempts the owner-only daily digest when LIST_DIGEST_ENABLED=true and Central local time is at least07:00. NOTIFICATION_EMAIL selects the owner mailbox. Existing EMAIL_LIVE_ENABLED, sender credentials, authorized recipient list and suppression checks still apply. The date-derived message UUID and immutable reserved report prevent a changed daily snapshot or uncertain provider result from becoming another email. Only matched SendGrid delivery events confirm delivery. On-time means delivered no later than07:30 America/Chicago, not merely accepted before07:30.

Reconciliation assigns one task for uncertain attempts, adverse provider events or missing delivery by deadline. Tasks remain available for operator acknowledgement after recovery. Missing owner email still runs deadline reconciliation. LIST_DIGEST_ENABLED defaultsfalse. Manual admin scan does not send emails. Concurrent busy scans do not enter digest delivery.

## Schedule proposal — not installed

Use an authenticated five-minute worker invocation throughout the day to cover timely failure detection,07:00 send and receipt reconciliation. Proposed Vercel entry (add only after platform support and deployment acceptance):

```json
{"path":"/webhooks/_worker/daily-lists","schedule":"*/5 * * * *"}
```

The application handles America/Chicago windows, including DST. Keep existing seller-nurture cron and recipient gates unchanged. Vercel documents CRON_SECRET bearer delivery and duplicate/concurrent invocation behavior: https://vercel.com/docs/cron-jobs/manage-cron-jobs . Its Hobby tier cannot run this five-minute schedule and lacks the necessary timing precision: https://vercel.com/docs/cron-jobs/usage-and-pricing . Read-only team lookup confirmed team_XZeRcNxzGjDXsr7Z2AqwhfAe / julysses-projects but returned no plan. Do not assume the user's Supabase Pro upgrade changes their Vercel plan. Verify supported Vercel plan or an approved authenticated scheduler before installing; don't weaken deadline requirements to fit an unsupported tier.

## Required live evidence

1. Confirm full branch review, production schema reconciliation, exact deployment SHA and provider gates before activation.
2. Verify production-only CRON_SECRET is present without exposing its value; reject wrong/missing bearer secrets and verify the configured scheduler invokes the exact production worker.
3. With only the authorized owner mailbox allowed, run one controlled digest with LIST_DIGEST_ENABLED=true. Inspect immutable recipient/message/body reservation, one email claim, provider acceptance, signed recipient-matching delivery event, and user inbox confirmation. Reinvoke and prove no second provider send.
4. Simulate reservation-before-send interruption and uncertain send in isolation. Never replay uncertain live attempts; reconcile provider events or use an explicit operator recovery procedure.
5. Confirm a07:00–07:30 Central scheduled run and actual on-time delivery. Show missed/blocked/incomplete sources and zero-record complete sources distinctly. Check one missed-deadline task and after-hours ownership.
6. Require an independent monitor for a completely missing worker/scan: the in-process digest monitor cannot alert when the worker never runs. Seven-day reconciliation/lookback does not prove longer outage recovery.

No controlled digest email or scheduled acceptance occurred in this implementation session. These are open launch gates.
