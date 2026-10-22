# Buyer enrollment — October 22 candidate

Status: implemented and locally tested; not published, enabled or carrier-approved.
Eighteen allowlisted migration proposals remain unapplied. No buyer invitation,
SMS, email, registration purchase or production configuration was executed.

## Consumer and operator flow

The public routes are `/buyer-sms`, `/buyer-sms/privacy` and `/buyer-sms/terms`.
They mount outside operator login. Program details remain unavailable until the
exact configured brand, support, origin and policy version have been reviewed.
Enrollment itself has a separate default-off flag. Changing wording or identity
changes its hash and closes enrollment until the new version is explicitly approved.
Approved policy text can remain readable while new enrollment is paused.

An approved administrator prepares a private link after the buyer requests it.
The app never sends that invitation. The browser generates a 256-bit capability,
keeps it in the fragment (not server URL paths/query strings) and sends it only in
same-origin JSON requests. The database retains only its SHA-256 hash. Links are
bound to the current normalized buyer number, expire after seven days and accept
one immutable choice. They do not prove phone ownership. There is no public buyer
lookup or public response containing existing buyer profile details.

The optional checkbox starts unchecked. The consumer may request texts or keep
buyer SMS off. Server-side disclosure version and invitation snapshots must match;
changed numbers, inactive/deleted buyers, expired/unknown links or unapproved
configuration cannot accept a new choice. Consumer input cannot replace disclosure
text or grant operator authority. Choice/receipt requests retain stable references;
reloading can recover a saved receipt without replaying submission. Unknown saves
freeze the original payload; known rejection permits correction only after an
empty saved receipt is confirmed. Successful public and operator enrollment responses are
marked no-store and no-referrer.

A positive submission creates immutable evidence, an assigned due review task and
an operator notification; it does not set SMS opt-in. The administrator reviews
the exact saved choice/disclosure and number, then a separate server-only review
copies the retained evidence into the consent ledger and completes the task.
A refusal disables buyer SMS immediately. A newer refusal remains effective even
if an older positive request is reviewed later or the legacy boolean is toggled.
Existing global DNC is never cleared. No homeowner or AI-call consent is granted.

The operator panel shows dated evidence, fingerprints and reviewed status in
20-row pages with a total count. Raw evidence remains private and survives buyer
deletion. Exact retries cannot overwrite it. Public callers have no SQL/table
access; only three exact configuration/receipt/submit API method/routes bypass
operator login. Administrator operations still verify current profile role/status.
No automatic confirmation text, enrollment email or campaign activation is added.

## Policy and release review

The proposed owner-facing wording is saved in the local task file
`BUYER-SMS-PROGRAM-REVIEW.md` (outside the repository). It contains the complete
checkbox, privacy and terms text, public support details and exact proposed version.
It is not a claim that those URLs are live or that policies have been approved.
The public business pages were read on October 22 and still restrict consent to
homeowner inquiries, explicitly excluding unrelated marketing. The buyer program
must remain separate; cross-link its published form from the official website and
verify the hosted form domain with the carrier before registration.

Review needed: factual brand/support/data-handling confirmation and exact wording,
public publication and source proof, priced carrier registration approval, actual
approved route, fresh controlled handset delivery/reply/STOP, signed-in operator
acceptance, deployed artifact/JWT/tenancy and exact release/rollback. Buyer SMS
remains required and not accepted for launch. Existing broader source/PropStream,
volume/APN and manual CRUD/classification gates remain in the Friday matrix.

## Evidence

Real API/PostgreSQL tests cover public boundaries, administrator-only invitations,
hashed/expired/wrong-number capabilities, exact policy version, immutable choice,
positive pending review, immediate refusal, stale-positive refusal protection,
lost committed responses, disabled-program receipt recovery, private table/RPC
role denial, task assignment/completion, retained deletion history and zero SQL
network actions. Frontend tests cover unchecked choice, public policy rendering,
receipt reload, stable/frozen unknown retry, known rejected correction, disabled
program state and invitation preparation without sending.

Backend 1,370 passed / 10 skipped; frontend 327 / 62 files; build/typecheck, API-only
cold start and lint gate pass (142 existing findings). Full eighteen-proposal
upgrade/rollback/preservation and connected intake journeys are recorded in the
current upgrade result, with a final targeted enrollment rehearsal for response
headers. Providers/Auth are stubbed at documented boundaries, not handset evidence.

Primary references: [Twilio consent policy](https://www.twilio.com/en-us/legal/messaging-policy),
[public business SMS scope](https://thejaysdallas.com/sms),
[existing privacy policy](https://thejaysdallas.com/privacy-policy),
[existing terms](https://thejaysdallas.com/terms).
