# WholesaleOS operational review and launch status

Updated October 16, 2026, after the 22:06 UTC tax transfer. Repairs are deployed and historical inventory is in production. **Full automated launch is not yet verified. Collection and SMS remain paused.**

## What is now working

| Process | Verified result | Remaining boundary |
|---|---|---|
| Restricted county intake | Actual production Edge request accepted one approved historical Collin notice (HTTP 202); identical replay returned HTTP 200/replayed=true. One saved batch and record. | Fresh collection and unattended scheduling are not yet proven. |
| CRM association and follow-up | The test reused the existing lead/property and pending assigned follow-up. No duplicate lead, property or task. | New candidates still need property identity and current status evidence. |
| Historical source handoff | Dallas and Collin foreclosure evidence and canonical tax snapshots are now in production with original receipts and dates. | Historical snapshots do not prove current county coverage, active foreclosure or current debt. |
| Review workflow | Live source filters, stable pagination, per-source counts and unchanged global counts verified. | 40,268 records still require evidence; this is a review inventory, not a qualified campaign. |
| CSV lead import | Authenticated server reconciliation preserves notes/motivation, identifies existing matches and rejects uncertain updates. | Operator acceptance for the complete daily workflow remains necessary. |
| Website owner alerts | Durable owner alert is claimed before SMS scheduling; an SMS scheduling exception no longer prevents owner notification. | Remaining historical alerts need evidence reconciliation, not mass resend. |
| After-hours SMS scheduling | New inquiries defer to the next 9 AM America/Chicago contact window, including DST; expiry follows that window. Existing jobs are preserved. | Scheduler is paused; this repair does not establish delivery. |
| Monitoring | Retell failures, unconfirmed delivery, stalled/review jobs and intake handoff outcomes are monitored. | Delivery callbacks and actual handset outcomes require provider acceptance. |

## Production inventory

| Source | Saved source records | Awaiting evidence |
|---|---:|---:|
| Dallas foreclosure | 490 | 489 |
| Collin foreclosure, including the approved transport test | 165 | 81 |
| Dallas tax snapshot | 30,516 | 30,516 |
| Collin tax snapshot | 9,182 | 9,182 |
| Total | 40,353 | 40,268 |

The identical second Collin tax snapshot was excluded. The tax transfer created zero leads or properties and two pending review tasks assigned to the approved owner. Production has 17,448 leads, 138 tasks, 82 associated properties and 77 trace requests. Tracing count and SMS-event fingerprint stayed unchanged throughout the intake acceptance and tax transfer. All source gates, outreach, spending and SMS scheduler remain disabled.

Existing PropStream history was preserved earlier: 77 completed requests and 481 contacts. Prior contact review found 146 DNC-listed and 335 DNC-unknown; no new contact-clearance review was performed in this continuation. Keep them on hold until current channel permissions are verified. Retain PropStream and the cumulative $50 prepaid cap; no reloads, new purchases or subscriptions were made.

## SMS blocker

Both provider cases were refreshed after the latest intake work. [Twilio ticket 29953072](https://help.twilio.com/tickets/29953072) remains Hold, with an internal escalation and latest response October 15 at 6:18 PM as displayed. [Retell ticket 65825](https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825) remains Open with acknowledgement only.

The owner test was accepted by Retell but marked undelivered by Twilio with error 30007. The failed message lacked a Messaging Service SID, while an earlier delivered message used the registered service; that difference is an investigation lead, not a proven cause. Supported routing and delivery-callback linkage still require resolution. No test retry, support message or sending-worker invocation occurred in this continuation.

Keep Twilio and Retell. Before resuming automatic acknowledgements, use the short campaign-aligned inquiry acknowledgement already drafted in `retell-carrier-support-draft.md`, confirm the supported route and callback path, then verify actual delivery. Do not substitute repeated sends or relaxed suppression rules for provider resolution.

## Verification and release

Live runtime: e86c92d55905b3e545a08fae64637ff50612df4a, Vercel deployment dpl_6doVwKbFKCHgSMQtMgzeSxxwPMbd, READY with wholesale-automation.vercel.app assigned and no alias error. GitHub CI 38972159798 succeeded. The source-filter migration is applied; its RPC denies direct execution to anon/authenticated and permits the server service role.

Latest filter validation: 131 pipeline tests, 18 targeted backend tests, frontend onboarding regression, production build and lint regression gate passed (149 existing lint findings, zero new). The earlier full backend suite passed 794 tests and frontend suite passed 162; these are earlier full-suite results, not rerun counts from the tax transfer.

Production rollback assertions passed for the exact intake linkage and tax transfer before commit. All 81 tax batch payload/record SHA256 values matched the original receipts; authoritative PostgreSQL row checksums matched both source snapshots and imported rows. Final read-only checks verified completed receipts, one assigned task per county, correct counts and paused controls. Automatic approval review rejected a second committing promotion run; it was not executed. The completed-state guard was inspected, and saved-state checks replaced that extra run.

Authenticated browser checks verified Dallas/Collin filters, empty tax states before import, populated tax states after import, pagination reset on source change and the global count. CRM health, Daily Lists and both website intake pages return HTTP 200. Availability is not end-to-end submission or handset evidence.

## Remaining work before full launch

1. Resolve Twilio/Retell filtering, supported A2P routing and delivery callback linkage. Keep sending paused until verified.
2. For both Hilltop and Jays, observe a fresh consented inquiry through receipt, deduplicated CRM lead, assigned task, owner notification, handset delivery, reply history and STOP suppression. Preserve cooldowns, original STOP history and uncertain/accepted job holds.
3. Reconcile the remaining legacy intake and owner-alert exceptions against delivery evidence. Do not reopen closed historical test leads or replay ambiguous notifications.
4. Validate current county evidence and coverage, then explicitly resume one supervised unattended GPT collection cycle. Confirm original source receipts, deduplication, owner assignment and CRM history before scaling. The one-record exception did not resume scheduled collection.
5. Resolve unknown DNC status and establish channel permission before exporting contacts for outreach. A tax record, foreclosure notice or returned phone number does not establish SMS permission.

Recommended launch approach: use the CRM for reviewed inventory and human follow-up while these checks are completed. Release automated outreach only after the provider and real-user acceptance checks pass. No fully operational or successful automated campaign claim is made.

## Resume references

- `START-HERE-NEXT-CHAT.md`: newest state first, exact receipts, IDs, private evidence paths and next steps.
- `onboarding-release-manifest.json`: applied migration sequence and promotion receipts.
- `pipeline/operations/promote_tax_20261016.sql`: executed historical operation; do not rerun merely to inspect status.
- Branch `codex/retell-sms-production`. Pull before edits; commit and push each logical update.
- Production Supabase dvzhzlipbwzzcliujzyz; rehearsal tbhwxgfzbiaqjurghntj.
- Restricted intake credentials expire January 14, 2027; rotate before expiry. Plain tokens remain in their scoped Mac Keychain entries.
