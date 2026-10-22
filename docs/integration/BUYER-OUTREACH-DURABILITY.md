# Buyer outreach durability — October 22 candidate

This is candidate evidence, not a production release or buyer SMS acceptance.
The fifteenth allowlisted migration is
`20261022194256_integration_buyer_outreach_claims.sql`; all fifteen are unapplied.

Verified operator identity and stable campaign UUID derive one immutable attempt
per buyer/channel. A service-only SQL transaction checks active state, current
consent/destination and suppression, then persists the attempt and public log
before any provider call. Missing schema/log failure never authorizes sending.
Retries validate exact identity/content; unknown claims never authorize takeover.
Existing native email claims store provider acceptance. Unknown mailbox submissions
hold later campaigns and stop remaining batches. Explicit reconciliation reads
saved results only, with zero provider calls and operator ownership checks.

Public history retains a buyer snapshot after deletion (nullable FK with SET NULL).
Approved browser reads remain; browser insert/update/delete are denied. Historical
rows are preserved by upgrade and rollback rehearsals. Private attempt identity
cannot change or be deleted through the application protocol.

Signed SendGrid event normalization and storage remain native. A trigger binds the
app UUID plus recipient/provider, stores event ID separately from the API submission
header and mirrors delivered/failure evidence. Opens/clicks do not imply delivery.
Contradictory terminal evidence is an unknown review hold; old processed events
cannot erase delivery. API acceptance is not handset/inbox delivery.

Primary identifier references: [X-Message-ID](https://www.twilio.com/docs/sendgrid/glossary/x-message-id),
[message ID](https://www.twilio.com/docs/sendgrid/glossary/message-id),
[event webhook](https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/event).
No prefix-based conversion between submission and event identifiers is used.

The real SQL/API harness uses synthetic example.test recipients, signed synthetic
callbacks, eight independent database sessions and a stubbed provider transport.
It covers repeat/content conflict, rollback before dispatch, lost committed claim,
lost result response, explicit recovery, wrong signature/recipient, suppression,
contradictory receipts, deletion retention and browser write denial. All provider
calls are local stubs. Backend 1345/10 skipped; frontend 308/60 files; build and lint
gate pass (142 existing findings); API-only cold start passes. The full restored
catalog, fifteen-proposal upgrade/rollback and ten intake journeys pass.

Open: REQUIRED buyer SMS (see BUYER-SMS-LAUNCH-GATE.md), actual SendGrid configuration
and live receipt/inbox acceptance, buyer email reply routing, signed-in review,
production-volume locking, tenancy/JWT review and artifact/rollback acceptance.
The current Mailgun transport has no equivalent buyer delivery mirror proven here.
No scheduler, flag, credentials, live schema or provider configuration was changed.
