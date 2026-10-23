Current update: the dedicated transport now enforces this reviewed consent and
current suppression at reservation and final authorization. Readiness reflects
the current route/consent checks. See BUYER-SMS-TRANSPORT.md. No real route is
approved/enabled; consumer enrollment and carrier/handset acceptance remain open.

# Reviewed buyer SMS consent — candidate October 22

The sixteenth unapplied proposal adds a private immutable record of an
administrator's review of retained written evidence. It is one prerequisite for
required buyer SMS, not a sending implementation or carrier approval.

Buyer profile → Buyer SMS consent opens a separate read. A failed read is not
no-consent proof. Approved operators can inspect the current number's latest
review; only an approved administrator may record one. The server checks the
stored profile role/status, never client-provided role metadata.

A review includes a stable UUID, the exact current normalized phone, retained
HTTPS evidence reference (without URL credentials), SHA-256, source type, actual
consent date/time zone, exact written disclosure, affirmative buyer action and
administrator attestation. Verbal calls/contact imports are not accepted sources.
The app does not fetch or cryptographically verify the external artifact or prove
phone ownership: the administrator must inspect real evidence for the correct
brand and buyer deal-alert program. A hash or pasted text alone is not proof of
consumer consent. Published consumer enrollment and campaign approval remain open.

The append-only record survives deletion of buyer/operator rows. Exact retries
recover the same result after lost acknowledgement. Changed identity/evidence
cannot reuse a reference. Later refusal records are preserved and prevent the
old accepted review from becoming current merely through a late retry or boolean
change. Current phone changes have no inherited consent. All formatted phone DNC
and existing seller DNC checks remain effective. A review never clears suppression.

No SMS is sent or scheduled. The existing buyer route remains unavailable even
after a positive review. Historical inquiry consent, purchased contacts and a
legacy sms_opt_in boolean are insufficient for this review status. The future
buyer transport MUST enforce this receipt and current suppression itself; this
checkpoint does not claim that transport has been implemented.

Verification: real API/PostgreSQL with synthetic written evidence, authenticated
admin/nonadmin, malformed/future/zone-free dates, unreviewed/invalid sources,
exact retry and changed evidence, lost committed response, actual unavailable SMS
attempt, phone changes, later refusal, late replay, DNC formatting, deletion
retention, immutable trigger and browser role denial. Frontend tests cover access,
read failure, payload/reference retention, suppression and inert evidence display.

Sources: [Twilio consent policy](https://www.twilio.com/en-us/legal/messaging-policy),
[Advanced Opt-Out](https://www.twilio.com/docs/messaging/tutorials/advanced-opt-out),
[Supabase privileges/security](https://supabase.com/docs/guides/database/postgres/row-level-security).
Provider account findings and registration draft are in
`BUYER-CAMPAIGN-REGISTRATION-DRAFT.md`. No production changes/provider calls.
