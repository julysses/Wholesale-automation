# Retell form SMS scheduler

The cloud scheduler polls every 10 seconds. A form response becomes eligible at submission + 60 seconds; the intended handoff is therefore about 60–70 seconds after submission under normal load, plus provider/carrier delay. Exact handset delivery at 60 seconds is not guaranteed. Measure the actual owner test before claiming readiness.

Migration `20261015181957_retell_sms_scheduler.sql` installs an inactive cron job and disabled private configuration. It does not transmit credentials, invoke HTTP, enable messages, or change county collection. Rehearsal only has been migrated.

The private function accepts only the two known WholesaleOS worker URLs. It invokes the existing authenticated worker only for due jobs or stale claims requiring reconciliation, suppresses overlapping requests for up to 90 seconds, and stores only the request ID/time. The existing worker retains consent, suppression, recipient allowlist, expiry and activation gates. An HTTP request ID is not delivery evidence.

Before activation:

1. Complete Retell/Twilio authorization and provider-native STOP/reply acceptance. Confirm the matching app deployment has all required migrations and callback logic.
2. Configure the worker's CRON_SECRET and approved Vault secret `retell_sms_worker_bearer` with the same value. Do not put secrets into git, logs or cron commands. Preview additionally requires `retell_sms_preview_bypass`; the owner approved this expanded storage on October 15. Both secrets are now stored in rehearsal Vault, with the worker credential matching the branch-only Vercel CRON_SECRET. The migration itself contains no secrets.
3. Choose the matching endpoint in `private.retell_sms_scheduler`. Never point rehearsal queue management at production merely to bypass deployment protection.
4. With application SMS gates OFF, enable the scheduler configuration and cron job for a bounded HTTP acceptance test. Verify unauthorized requests fail, authorized requests return sending_enabled=false, and no provider attempt occurs. Compare cron history with `net._http_response` using the stored request ID; restrict access because underlying HTTP request headers contain credentials.
5. Set the finite owner test recipient, published agent version and approved sender identity; verify both public seller forms route to the intended environment. Enable dispatch only for the authorized test after all other acceptance checks. Measure submission, due, claim, Retell acceptance and handset receipt timestamps separately.
6. Check duplicate submissions, late replies and provider-level STOP. Unknown provider outcomes stay in review and must never be automatically resent.

Disable the trigger with `cron.alter_job(jobid,active:=false)` for the job named `wholesaleos-retell-form-sms`, and set private configuration enabled=false. Keep application live gates OFF independently. Cron run history requires a separately reviewed retention policy before long-term activation; Supabase does not automatically prune it.

References: [Supabase Cron](https://supabase.com/docs/guides/cron/quickstart), [pg_net](https://supabase.com/docs/guides/database/extensions/pg_net), [Retell SMS setup](https://docs.retellai.com/deploy/enable-sms).
