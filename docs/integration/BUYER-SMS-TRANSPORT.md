# Dedicated buyer SMS transport — October 22 candidate

Status: implemented and verified locally; NOT deployed or approved for live sending.
Buyer SMS remains REQUIRED for the launch. All seventeen proposals are unapplied.
No live sender/campaign is created or enabled by this work.

## Sending and recovery

A separate buyer sender/service/campaign/brand must be configured. Global SMS and
buyer SMS flags default off. There is no fallback to the homeowner sender/service.
A private database route record must also be explicitly approved/enabled with
retained proof; the application service role can only read route records. This
proposal seeds no approved route, and flags alone never authorize sending.

The operator checks readiness and reviews the full branded copy and STOP/HELP
footer. The server checks the launch allowlist, Texas sending window/weekend rule
and 1,600-character maximum. Each buyer is independently checked for active status,
current number, immutable reviewed written consent and current suppression.

One SQL transaction persists the stable request/buyer attempt, public saved log,
route/body/consent snapshot and native reservation before dispatch. A final one-way
SQL authorization rechecks consent, phone, suppression and route approval. Consent
reviews and final authorization use the same phone/row lock order. A STOP committed
before authorization prevents create. Already authorized in-flight work can race a
later opt-out; carrier opt-out enforcement and live acceptance must be verified.

The SDK has a five-second timeout and zero retries. At most one create call follows
a new confirmed authorization. Lost reservation/authorization acknowledgement never
permits takeover or replay. A known SDK SID can be stored again after a lost result
response without a second SDK create. Uncertain submissions hold later batches and
future requests for the number. Each normalized number has at most one buyer SMS
attempt per Texas calendar day; a shared destination receives at most one message
in a campaign. Daily/consent/route skips remain visible in saved history.

API acceptance, carrier delivery and handset observation remain separate evidence.
Saved-request reconciliation reads stored outcomes only and never calls a provider.
The original inquiry transport and signatures retain their defaults.

## Callbacks, replies and STOP

Dedicated routes: `/webhooks/buyer-twilio/status?message_id=…` and
`/webhooks/buyer-twilio/inbound`. The account-token SDK validator authenticates the
configured public URL and all form fields before storage. Sender, account,
recipient, request reference and provider SID bind status evidence to a saved
attempt. Callback storage runs outside the async event loop. Saved snapshots
remain authoritative after sending is paused; keep historical sender configuration
and route records available until outstanding events are resolved.

Accepted/queued/sent never imply delivery. Late acceptance/queued callbacks cannot
regress delivered evidence. Contradictory terminal outcomes or SIDs become a
persistent review hold. Signed raw events are immutable and exact duplicates do
not duplicate tasks. Event reference/content conflicts fail closed for review.

Buyer replies create a retained inbound log, operator notification and due task.
Ambiguous shared identities or deleted buyers are routed for human review; a reply
never invents consent or a lead. Missing ownership returns a retryable failure;
the same receipt can recover assignment without reopening completed work or
sending SMS. Replies never fall through to inquiry AI automation. No automated
buyer reply email is implemented by this checkpoint.

STOP uses the native transactional DNC path, disabling matching buyer eligibility
and cancelling pending buyer reply tasks. Native inquiry STOP also suppresses
buyers. START records the event without restoring consent or clearing DNC. Known
carrier opt-out rejections preserve suppression without fabricating a provider SID;
contradictory prior delivery remains held. No duplicate STOP/HELP SMS is generated
by the application; provider opt-out configuration still needs live verification.

## Evidence and remaining release gates

Real PostgreSQL/API tests use synthetic route records, signed synthetic callbacks
and a stubbed SDK create. They cover missing consent; route/flag fallback refusal;
content conflict; late and contradictory callbacks; deletion retention; reply/task
idempotence; owner recovery; STOP/START; opt-out rejection; lost reservation,
authorization and result responses; rollback before dispatch; shared destinations;
eight competing sessions/one create; browser authority denial; immutable identity;
paused receipts and non-sending reconciliation. Unit tests cover window boundaries,
weekends, copy limits, launch allowlists and unconfirmed route approval. UI tests
cover explicit readiness, full reviewed copy, failed/malformed readiness and no
sending from consent inspection.

Backend 1,370 passed / 10 skipped; frontend 320 / 61 files; build/typecheck and lint
gate pass (142 existing findings). API-only cold start passes. Full seventeen-
proposal apply/rollback/preservation and ten connected intake journeys pass. A
fresh buyer-only replay additionally verifies the final async callback handler.
No real provider calls, production mutations, purchases or scheduler activation.

Still required: real consumer enrollment and policy/terms coverage, approved and
priced buyer campaign/sender, exact scoped live flags/allowlist, actual handset
receipt/reply/STOP, signed-in operator acceptance, JWT/tenancy review, deployed
artifact/interpreter verification and reviewed release/rollback. The current
provider timeline does not establish a Friday buyer-SMS launch. See
`BUYER-SMS-LAUNCH-GATE.md` and `BUYER-CAMPAIGN-REGISTRATION-DRAFT.md`.

Primary references:
[Twilio callback signatures](https://www.twilio.com/docs/usage/webhooks/webhooks-security),
[message status](https://www.twilio.com/docs/messaging/api/message-resource),
[callback routing](https://www.twilio.com/docs/messaging/guides/track-outbound-message-status),
[Advanced Opt-Out](https://www.twilio.com/docs/messaging/tutorials/advanced-opt-out).
