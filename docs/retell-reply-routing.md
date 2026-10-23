# SMS reply and STOP routing — acceptance status

Keep Twilio Messaging Service inbound pointing to WholesaleOS. The number-level Retell URL alone is overridden by that service setting. Do not switch the service to defer-to-number until suppression continuity is proven.

The app now authenticates the carrier request, commits its receipt, phone-wide suppression, notification and high-priority follow-up, then may return a POST TwiML redirect to the fixed Hilltop Retell webhook. Natural-language opt-outs are classified only after signature validation. STOP cancels pending SMS follow-ups for matching leads; START never restores CRM permission. Completed tasks stay completed. CRM timelines include carrier inbound receipts as well as Retell transcripts.

`RETELL_SMS_REPLY_ROUTING_ENABLED` is absent/default OFF. The handoff also requires every existing form-SMS activation gate, finite recipient allowlist, contact hours, current matching consent, a nonsuppressed receipt, and exactly one accepted form chat matching the receipt's lead. Control messages (STOP/HELP/START variants), duplicates and unknown/ambiguous conversations never forward. A receipt failure returns503 before handoff. Later routing-check failures retain the receipt and human task without automatic replay. No arbitrary destination or credential forwarding is permitted.

This is an **unverified provider handoff**, not a proven native integration. Twilio documents POST TwiML Redirect; Retell documents the direct number webhook. Neither establishes compatibility of this intermediary path. Before enabling production, the owner-only test must show the original MessageSid/From/To/Body reach Retell once, the existing chat continues with its original metadata, no unsolicited new chat starts, and CRM callback receipts/follow-ups persist. Do not enable an inbound default agent to work around unknown-chat holds. Human follow-up remains the fallback. A carrier receipt plus a Retell transcript can currently produce separate follow-up tasks; consolidate based on real provider IDs after the first accepted test rather than infer identity from message text.

When Retell omits metadata on later callbacks, only an exact saved chat ID plus matching remote phone can resolve the CRM lead. Unknown or ambiguous chats remain rejected. STOP carrier receipts still protect the phone even if a Retell transcript is missing.

## Verified October15

-100 targeted Python tests passed (signature validation, receipt persistence, STOP, handoff gates, missing metadata, form scheduling, timeout/duplicate handling).
- Rehearsal SQL rollback test `tests/sql/twilio_retell_reply_routing.sql` passed: ordinary reply, duplicate, two leads sharing a phone, STOP, late reply, START and completed task preservation; no retained QA data.
- Migrations20261015184900 and20261015185153 applied only to rehearsal. The second preserves compatibility with older callbacks missing the derived natural-language opt-out field.
- Scheduler remains disabled; phone agents remain None; no carrier message or Retell chat initiated.

## Remaining before the public website test

1. Verify deployed preview and CRM display. Keep live flags off.
2. Finish Retell API credential and pinned published SMS-agent configuration. Existing webhook signing credential is not permission to silently broaden its dispatch role.
3. Reconcile selected production migrations/code and actual public form destinations. Do not promote the entire collector rehearsal branch without review or send public submissions into rehearsal.
4. User wants to enter their own number through the form rather than post it in chat. Identify that test submission with the user, then configure its exact number as the finite test recipient; do not assume a random latest submission is theirs. A send-disabled intake test does not send a text and must not be presented as the final timing test.
5. After no-send checks, obtain authorization to activate the finite real test. Keep general dispatch off. Measure both seller forms separately. Existing24-hour duplicate protection may intentionally block the second form on the same phone; use a bounded, reviewed test procedure rather than weakening global deduplication.
6. Test ordinary reply and STOP on the handset; require CRM suppression and cancelled follow-up. Restore all sending/route/scheduler gates OFF afterward.

Sources: [Twilio Redirect](https://www.twilio.com/docs/messaging/twiml/redirect), [Retell SMS setup](https://docs.retellai.com/deploy/enable-sms).
