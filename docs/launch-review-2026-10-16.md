# WholesaleOS operational review and recovery
Updated October 16, 2026. Status: repairs deployed; full automated launch NOT yet verified.

## Outcome
The failures span separate stages. Website intake has persisted leads, but an SMS scheduling exception could prevent owner alerts. CSV uploads bypassed the server's reconciliation and could create duplicates. Retell's consented test was filtered downstream, and monitoring excluded Retell events. Bulk collection and its saved contacts remain in rehearsal, not production.

## Completed repairs
| Change | Evidence | Git commit |
|---|---|---|
| Active Leads CSV uploader now uses authenticated server reconciliation, preserves motivation/notes, and reports imported versus existing matches. A missing update result fails explicitly. | Regression tests reproduced lost fields and false-success updates before repair. UI test verifies server route and no retry on uncertain failure. | ae12ad9 |
| Durable owner alert is claimed before seller SMS scheduling; scheduling errors no longer abort owner email. Uncertain sends are not replayed. | Two failing regression cases passed after repair. | 2dec1ff |
| Launch monitoring includes Retell outbound failures, unconfirmed delivery after 24h, and review/stalled form-SMS queue entries. | Production SQL regression failed before repair and passed after; synthetic records rolled back. | f5f7934 |

App deployment dpl_2BvKJ7GubD9sxKfMouRgA1DmHzBQ is READY and serves wholesale-automation.vercel.app at 2dec1ffeed7e272e33ad0e8adcfdb6571b0db885. Monitoring migration 20261016191327_monitor_retell_sms_outcomes.sql was applied separately to production. All three code updates pushed to origin/codex/retell-sms-production.

## Verification completed
- Backend: 709 tests passed. Frontend: 142 tests across 33 files passed; production build passed.
- Lint: no new findings from repairs; 149 preexisting findings remain.
- GitHub CI passed for application repair commits ae12ad9 and 2dec1ff.
- Production rollback SQL verified public inquiry replay/conflict handling, consent preservation, atomic lead/task creation, distinct inquiries, and browser access restrictions.
- Production rollback SQL verified SMS timing, single claim, shared attempt ledger, cooldown, expiry and suppression. Monitoring regression verified failed/accepted/delivered outcomes, queue review/overdue/stopped states, and access restrictions.
- Post-deploy read-only availability check: CRM readiness, Hilltop website and Jays website all true.
- These checks do not prove handset delivery, a live reply/STOP cycle, a fresh website submission through every external provider, or unattended collection.

## Current operational evidence
### Website intake and follow-up
32 processed website submissions link to leads: 16 Hilltop and 16 Jays. 30 have linked tasks and 29 are assigned. Two missing tasks are historical September 29 submissions. One July 10 pending receipt has no form/lead linkage; reconcile manually rather than replay it. Four intake-alert findings also need reconciliation of existing delivery evidence before retrying anything.

The first SMS window expires 15 minutes after submission, while contact hours are restricted. An after-hours inquiry can expire without a next-day SMS. Decide and implement an explicit next-business-window acknowledgement policy, retaining consent and suppression controls. Accepted/review jobs and shared cooldowns intentionally prevent blind resend.

### Carrier and Retell
Production automatic SMS scheduler is disabled and its cron inactive. Environment send flags remain enabled: do not manually call the sending worker as a diagnostic.

Twilio ticket 29953072 was read after renewed login: Carlos Ospina confirmed internal escalation; status Hold, last updated October 15 at 6:18 PM as displayed. No technical resolution supplied. Retell ticket 65825 remains open with acknowledgement only.

Failed consented SMS: SM0ad8ce793ccef33ea439760c1de917e0; Retell chat chat_3e830c21a691319298d4d773598. Error 30007 indicates filtering. Failed message lacked a Messaging Service SID; an earlier delivered message used MGaf5837f7a7cad183e8b38b1147728562. This is evidence for investigation, not a proven root cause. Delivery callback linkage from Retell to CRM is not verified. Existing Twilio callback matching only covers provider=twilio.

The current first-message prompt is a long investor pitch. A short inquiry acknowledgement draft already exists in docs/retell-carrier-support-draft.md. Review it against the approved campaign and supported provider route before publishing. Copy changes alone are not proof of delivery.

### Bulk leads and PropStream
Production has no wholesale_ingest schema. Rehearsal holds 77 completed PropStream requests, 481 contacts and 77 linked follow-up tasks. Recorded cost is zero; no spend or new tracing performed this session. All 481 contacts are held: 146 DNC-listed, 335 DNC-unknown. None is currently cleared for campaigns. A phone number or paid lookup is not SMS permission.

The daily 5 AM Chicago collection automation is paused because the prior chat explicitly paused work. No October 16 foreclosure receipts were generated. Do not label this a failed cron. The standalone Mac worker remains intentionally disabled in favor of the GPT workflow. Prior partial/missing source receipts still require operator review; a healthy supervision run does not mean successful collection.

Retain PropStream and the cumulative $50 prepaid cap. No new purchases, reloads, subscriptions or carrier retries were performed.

## Required path to full operation
1. Obtain Twilio/Retell's supported A2P route and delivery-status integration; resolve the filtering investigation. Keep automatic sends paused until then.
2. Publish campaign-aligned inquiry copy and verify a controlled, owner-approved fresh form inquiry: receipt → deduplicated lead → assigned task → owner notification → handset delivery → reply history → STOP suppression. Run for both website paths; never erase prior STOP history or replay accepted/uncertain jobs.
3. Reconcile the historical missing tasks and four unresolved owner-alert receipts with provider evidence. Assign accountable owners to imported leads; do not mass-replay notifications.
4. Selectively port the collector schema/service/UI changes into the newer production branch. Review schema dependencies and data reconciliation first; do not merge/promote the older collector branch wholesale. Run a small matched batch through production CRM before scaling.
5. Resume and observe one complete scheduled county collection run using docs/gpt-scheduled-bulk-workflow.md. Verify current-sale identities, completeness, receipts and CRM history; resolve missing/partial sources. Preserve paid-data cap.
6. Resolve unknown DNC status and document eligible outreach permission. Keep DNC-listed contacts suppressed. Then test one eligible bulk lead through assignment and its permitted follow-up channel.
7. Define next-business-window behavior, maximum acknowledgement age, and daily owner review of monitor incidents. Finish authenticated browser acceptance for import, lead details, tasks and history.

Full launch remains blocked by steps 1–6; no completion date or successful automated campaign is claimed. Website intake and owner follow-up can be used with human oversight while these gates are closed.

## Exact resume checkpoint
Production checkout: /Users/juliodominguez/Documents/Codex/2026-09-28/make-sure-to-review-my-wholesale/work/wholesale-sms-production
Branch: codex/retell-sms-production; latest code f5f7934. Pull before changes; commit and push each logical update.
Collector checkout: sibling wholesale-launch-prep, branch codex/dallas-collin-launch-prep.
Production database: dvzhzlipbwzzcliujzyz. Rehearsal: tbhwxgfzbiaqjurghntj.
Previous application deployment for rollback: dpl_F1jXupfYoa6HUx6C27SwzYg5e8nY (b94d086).
Tests: tests/test_master_list_import.py; tests/test_intake_notification_safety.py; frontend/tests/lead-import-reconciliation.test.tsx; tests/sql/retell_sms_monitor.sql; tests/sql/public_intake_reference.sql; tests/sql/retell_form_sms_production_qa.sql.
Python test interpreter: /Users/juliodominguez/Documents/Codex/2026-09-28/i-x20/work/launch-venv/bin/python.
Do not run historical reviewed_sms_resubscription_live_qa.sql unchanged against real records; its assumptions are stale.

## References
- Twilio support: https://help.twilio.com/tickets/29953072
- Retell support: https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825
- Twilio 30007: https://www.twilio.com/docs/api/errors/30007
