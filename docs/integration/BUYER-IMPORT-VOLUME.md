# Buyer import volume and lock verification

The connected local API/SQL rehearsal now tests the exact 5,000-row acceptance
boundary as both one buyer with 5,000 purchases and 5,000 distinct buyers with one
purchase each. Receipt totals and database counts must agree. The distinct-buyer
request is retried with its original reference and must return the historical
receipt without duplicates. A 5,001-row file remains rejected before persistence.

Observed PostgreSQL17.11 timings were 2.919 seconds and 7.606 seconds respectively.
These are local synthetic timings, not production MICRO capacity or live HTTP
latency proof. The existing table lock serializes buyer identity decisions for
the entire import; other writers may wait or refuse during that period.

With a separate session holding the buyer table lock, the API refused after
3.008 seconds, left neither buyer nor private receipt, and accepted the exact
same request after release. The test requires refusal within eight seconds to
detect a missing database lock bound; it does not establish a network timeout.

APN constraints retain their existing conservative behavior: a different purchase
event for an already matched parcel requires review, never silently overwrites
or inserts a fallback. Future multi-county APN and repeat-sale semantics remain
a business/schema review gate. Zero production buyer history in the prior live
observation does not resolve those future semantics.

Import cleanup deletion is still a separate multi-request workflow whose partial
or lost-response recovery has not been established by these import-create tests.
No runtime, migration, provider or production setting was changed for this check.

Verification: full local production-upgrade runner exited0, including all21
allowlisted migration rehearsals, buyer workflows, and all10 intake journeys
(123.09 seconds for the intake suite). Auth and providers are synthetic.
The application runtime and proposed migration SQL are unchanged.

Cloud coverage: `scripts/run_offline_tests.py --buyer-import` is the dedicated
entry point added to the existing PostgreSQL17 buyer job. Prior run717 began
before this wiring change and does not prove the new assertions ran in Linux.
Its outcome must remain separate from the next run with this workflow change.
