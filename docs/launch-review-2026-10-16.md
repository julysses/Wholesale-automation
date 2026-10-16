# WholesaleOS operational review and launch status

Updated October 16, 2026, after the intake suppression fix and historical alert reconciliation. Repairs are deployed and historical inventory is in production. **Full automated launch is not yet verified. Collection and SMS remain paused.**

## What is now working

| Process | Verified result | Remaining boundary |
|---|---|---|
| Restricted county intake | Actual production Edge request accepted one approved historical Collin notice (HTTP 202); identical replay returned HTTP 200/replayed=true. One saved batch and record. | Fresh collection and unattended scheduling are not yet proven. |
| CRM association and follow-up | The test reused the existing lead/property and pending assigned follow-up. No duplicate lead, property or task. | New candidates still need property identity and current status evidence. |
| Historical source handoff | Dallas and Collin foreclosure evidence and canonical tax snapshots are now in production with original receipts and dates. | Historical snapshots do not prove current county coverage, active foreclosure or current debt. |
| Missing county address | Future parsing preserves missing situs as null; historical all-zero placeholders display as Unresolved property and cannot pass API address validation. Full-archive replay preserved account IDs, parcels and balances. | Original historical evidence remains unchanged. |
| Scheduled handoff | Paused heartbeat now reads the production checkpoint and corrected collector code instead of defaulting to rehearsal. | Schedule remains paused; a fresh observed run still requires approval. |
| Review workflow | Source filters, pagination and historical tax date/amount/warnings verified live. Exact Dallas and Collin property reviews saved through the production interface, with assigned follow-ups and preserved evidence. | 40,266 records still require evidence; historical tax balances do not establish current distress. |
| CSV lead import | Authenticated server reconciliation preserves notes/motivation, identifies existing matches and rejects uncertain updates. | Operator acceptance for the complete daily workflow remains necessary. |
| Website owner alerts | All three flagged owner emails have verified delivery receipts. Two stale intake holds were resolved with audited STOP/START and later-handoff evidence; seller follow-ups remain pending. | One alert still has an unexplained historical failed/blocked SMS outcome and remains under review. |
| Confirmed opt-out handling | Explicit confirmed suppression completes intake without creating an SMS job. | Unknown lookup results and unmatched consent still require review; original holds are not automatically rewritten. |
| After-hours SMS scheduling | New inquiries defer to the next 9 AM America/Chicago contact window, including DST; expiry follows that window. Existing jobs are preserved. | Scheduler is paused; this repair does not establish delivery. |
| Monitoring | Retell failures, unconfirmed delivery, stalled/review jobs and intake handoff outcomes are monitored. | Delivery callbacks and actual handset outcomes require provider acceptance. |

## Production inventory

| Source | Saved source records | Awaiting evidence |
|---|---:|---:|
| Dallas foreclosure | 490 | 489 |
| Collin foreclosure, including the approved transport test | 165 | 81 |
| Dallas tax snapshot | 30,516 | 30,515 |
| Collin tax snapshot | 9,182 | 9,181 |
| Total | 40,353 | 40,266 |

The identical second Collin tax snapshot was excluded. The tax transfer created zero leads or properties and two pending review tasks assigned to the approved owner. Subsequent reviewed tax associations created one Dallas lead and reused one Collin lead, with two properties and two assigned pending follow-ups. Production now has 17,449 leads, 140 tasks, 84 associated properties and 77 trace requests. Both tax signals remain inactive with current amount unknown. The Collin snapshot balance is $0.39; its existing lead qualification was preserved. The Dallas remaining levy is historical, not a verified current payoff. Tracing count and SMS-event fingerprint stayed unchanged throughout the intake acceptance and tax transfer. All source gates, outreach, spending and SMS scheduler remain disabled.

Existing PropStream history was preserved earlier: 77 completed requests and 481 contacts. Prior contact review found 146 DNC-listed and 335 DNC-unknown; no new contact-clearance review was performed in this continuation. Keep them on hold until current channel permissions are verified. Retain PropStream and the cumulative $50 prepaid cap; no reloads, new purchases or subscriptions were made.

## SMS blocker

At the last provider check on October 16, [Twilio ticket 29953072](https://help.twilio.com/tickets/29953072) remains Hold, with an internal escalation and latest response October 15 at 6:18 PM as displayed. [Retell ticket 65825](https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825) remains Open and now includes an October 16 reply escalating the issue to a telephony engineer; no technical resolution has been provided.

The owner test was accepted by Retell but marked undelivered by Twilio with error 30007. The failed message lacked a Messaging Service SID, while an earlier delivered message used the registered service; that difference is an investigation lead, not a proven cause. Supported routing and delivery-callback linkage still require resolution. No test retry, support message or sending-worker invocation occurred in this continuation.

Keep Twilio and Retell. Before resuming automatic acknowledgements, use the short campaign-aligned inquiry acknowledgement already drafted in `retell-carrier-support-draft.md`, confirm the supported route and callback path, then verify actual delivery. Do not substitute repeated sends or relaxed suppression rules for provider resolution.

## Verification and release

Live runtime: 3a318f2a1ad98709551f05284c4f92fdc25f40bd, Vercel deployment dpl_HQorig1iYLqKvm8Brq6a6vGQBYdF, READY with wholesale-automation.vercel.app assigned and no alias error. GitHub CI 38977524028 succeeded. The source-filter migration is applied; its RPC denies direct execution to anon/authenticated and permits the server service role.

Latest filter validation: 131 pipeline tests, 18 targeted backend tests, frontend onboarding regression, production build and lint regression gate passed (149 existing lint findings, zero new). The latest hosted release passed 844 backend tests plus six subtests and 165 frontend tests, alongside pipeline and real PostgreSQL checks. The missing-situs change also passed 12 local parser tests, 14 API tests and three UI tests.

Production rollback assertions passed for the exact intake linkage, tax transfer and subsequent two tax identity associations before saving. The tax reviews proved repeat deduplication, correct owner/follow-up, preserved original fingerprints and existing qualification, and no tracing or SMS change. Both live saves were then verified through UI queue removal and direct database receipts. The tax context migration preserves server-only permissions and accepts only the exact official Collin CAD dataset URL for the reviewed parcel. Security advisors remain at 29 INFO and three existing WARN findings.

Production rollback assertions also verified the historical transfer. All 81 tax batch payload/record SHA256 values matched the original receipts; authoritative PostgreSQL row checksums matched both source snapshots and imported rows. Final read-only checks verified completed receipts, one assigned task per county, correct counts and paused controls. Automatic approval review rejected a second committing promotion run; it was not executed. The completed-state guard was inspected, and saved-state checks replaced that extra run.

Authenticated browser checks verified Dallas/Collin filters, empty tax states before import, populated tax states after import, pagination reset on source change and the global count. CRM health, Daily Lists and both website intake pages return HTTP 200. Availability is not end-to-end submission or handset evidence. The affected historical Collin card was verified live as Unresolved property with an empty address input; no placeholder is linked to a CRM property.

## Intake-alert reconciliation

Open monitor incidents decreased from eight to six: two SMS, two form-SMS, one intake alert and one legacy intake. The two closed alerts retain original outcomes plus dated reviewer notes and evidence references. Their monitor tasks are completed; original seller follow-ups are still pending. Carrier failure incidents remain open. SMS events, scheduled jobs, DNC entries and re-subscription history were unchanged. No messages were replayed.

Local full validation passed 844 backend tests and 131 pipeline tests. Production rollback checks covered classification, exact historical reconciliation, preserved channel records and retained carrier failures before the actual save. Live setup monitoring displays six incidents.

## Remaining work before full launch

1. Resolve Twilio/Retell filtering, supported A2P routing and delivery callback linkage. Keep sending paused until verified.
2. For both Hilltop and Jays, observe a fresh consented inquiry through receipt, deduplicated CRM lead, assigned task, owner notification, handset delivery, reply history and STOP suppression. Preserve cooldowns, original STOP history and uncertain/accepted job holds.
3. Reconcile the remaining legacy intake and owner-alert exception against delivery evidence. Review forward handling of repeated website inquiries: three current exact phone/property groups contain six web-form leads, while submission-reference retry deduplication does not establish person/property deduplication. Preserve each receipt and consent; do not merge historical or uncertain matches automatically.
4. Validate current county evidence and coverage, then explicitly resume one supervised unattended GPT collection cycle. Confirm original source receipts, deduplication, owner assignment and CRM history before scaling. The one-record exception did not resume scheduled collection.
5. Resolve unknown DNC status and establish channel permission before exporting contacts for outreach. A tax record, foreclosure notice or returned phone number does not establish SMS permission.

Recommended launch approach: use the CRM for reviewed inventory and human follow-up while these checks are completed. Release automated outreach only after the provider and real-user acceptance checks pass. No fully operational or successful automated campaign claim is made.

## Latest tax-review evidence

The official Collin CAD daily publisher metadata identifies Collin Central Appraisal District at [Texas Open Data](https://data.texas.gov/api/views/ahis-pci3). The exact parcel response was cross-checked against source account, owner, situs and legal description. Dallas identity was verified in the official DCAD account and the saved appraisal archive; property ZIP was used instead of the owner mailing ZIP. Neither appraisal record establishes current tax payoff. Partial-interest and deferral examples remain held.

Private receipts and original evidence are preserved under `work/tax-property-review/`; exact IDs and next steps are in the resume checkpoint.

## Resume references

- `START-HERE-NEXT-CHAT.md`: newest state first, exact receipts, IDs, private evidence paths and next steps.
- `onboarding-release-manifest.json`: applied migration sequence and promotion receipts.
- `pipeline/operations/promote_tax_20261016.sql`: executed historical operation; do not rerun merely to inspect status.
- Branch `codex/retell-sms-production`. Pull before edits; commit and push each logical update.
- Production Supabase dvzhzlipbwzzcliujzyz; rehearsal tbhwxgfzbiaqjurghntj.
- Restricted intake credentials expire January 14, 2027; rotate before expiry. Plain tokens remain in their scoped Mac Keychain entries.
