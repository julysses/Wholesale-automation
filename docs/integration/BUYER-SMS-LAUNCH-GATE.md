# Required buyer SMS launch gate — Friday October 23, 2026

User decision: "Require buyer SMS at launch". Status: REQUIRED / NOT ACCEPTED.
Email readiness cannot close this gate. No promise of Friday readiness can be made
until provider and handset acceptance are proven.

Current implementation: tools/sms_client.py only authorizes consented property
inquiries and persists lead-bound sms_events. Buyer rows and an sms_opt_in boolean
are not that inquiry receipt. The candidate buyer dispatch deliberately records a
skipped buyer_sms_route_unavailable result and the interface disables sending.
Actual live carrier campaign scope has not been freshly verified. Local Twilio
account/token/service/from settings were absent in the current process; existing
Twilio console is signed out (confirmed after the timeout). No credentials were exposed or settings changed.

Next implementation sequence:

1. Verify the actual active Twilio messaging service, sending number, campaign use
   case/status, sample messages, opt-in description and STOP/help behavior through
   authenticated read-only access. If buyer deal alerts are outside the approved
   scope, prepare the exact registration change for review; do not relabel them as
   property inquiries. Provider approval timing may be an external Friday blocker.
2. Add immutable buyer-specific SMS consent evidence bound to normalized phone,
   disclosure version, source and timestamp. Imported contacts remain opted out.
   Define an operator-visible consent collection/review flow; do not backfill opt-in.
3. Implement a separate buyer transport/claim path using stable request/buyer IDs,
   durable pre-dispatch attempt/log, suppression checks and per-destination holds.
   Keep zero SDK retries after ambiguity and no takeover/replay of held attempts.
4. Add signature-verified Twilio status/reply handling bound to sender, destination,
   provider SID and saved buyer attempt. Preserve inquiry routing. STOP suppresses
   the phone across relevant buyer/inquiry paths; delivery is distinct from API
   acceptance. Unknown/conflicting outcomes hold for reconciliation.
5. Prove competing workers, lost acknowledgments, duplicate/out-of-order callbacks,
   no-consent/refusal, suppression, buyer deletion and role boundaries locally.
6. After configuration review, use the user's explicitly confirmed controlled phone
   for a fresh buyer opt-in, one allowlisted send and actual handset confirmation,
   reply/task history and STOP refusal. Facebook/Hilltop/Jays source tests may use
   that same number with fresh source receipts; never reuse held sessions.
7. Review exact release/artifact/rollback and owner acceptance before broad live
   sending. Keep general workers/cron/schedules paused until that review.

Pending owner details already requested: confirm controlled phone last four and
owner notification inbox. No new repeat request or inferred recipient is needed.
