# Explicit buyer analysis candidate — October 22, 2026

Status: local/full rehearsal and all nine Linux CI checks passed at44894b8; real-provider and production acceptance remain open.
This replaces log-only BackgroundTasks and queued-success UI for explicit buyer
rescoring/classification. The old write routes reject requests with recovery guidance.
CSV/manual intake does not automatically classify or score through this path.

Each operator creates a stable request before any work. Selected buyer membership
is frozen at start (maximum 20,000, refuse overflow); complete profile/history inputs
are frozen per buyer when claimed (maximum 5 MB, refuse overflow rather than truncate).
The retained timestamp controls free score recency and versions. Each explicit run
processes at most 20 buyers. Read-only checks and paginated results never perform work.

Paid classification requires explicit per-buyer confirmation, configured credentials,
a unique durable claim and a one-way final authorization. The existing initialized
Anthropic client now receives timeout=20 seconds and max_retries=0. One attempt uses
Haiku with a 512 output-token bound, a buyer summary and up to ten recent purchases.
Credential presence is not provider availability verification or live acceptance.
Lost claim/authorization responses are held; the same or another request cannot
repeat a potentially paid attempt. Cancellation prevents a late authorization,
but cannot undo or release an already-authorized unknown outcome.

Validated results are retained before application. Identical database-result retries
can recover lost acknowledgments without repeating the provider. Model output must
match the four types, finite confidence and bounded reasoning/tags. Invalid output
preserves the previous classification; it never fabricates a landlord. Suggested
tags remain suggestions in metadata, rather than verified facts. Existing custom
tags remain. Provider error details/secrets are not returned or logged by this path.

Application checks the entire buyer and ordered transaction snapshot atomically.
Changed/deleted inputs become stale/missing; no overwrite or resurrection occurs.
A committed score increments its version once. Consent, suppression, availability,
contact details and operator edits are outside the allowed patch. Concurrent history
committed after the application's SQL statement is newer evidence requiring a later
score; this is not a promise to serialize every future purchase forever.

Six private append-only tables retain request, claim, authorization, result, commit
and cancellation evidence. No buyer/user deletion cascade removes these receipts.
RLS plus service-only SECURITY INVOKER RPCs recheck current operator approval and
ownership. The browser receives bounded status/results, never claim snapshots/nonces.
Per-operator/tab saved browser references fail closed if storage is unavailable.
Unknown screen responses discard actionable stale status; recovery reuses the original
reference. New requests require an explicit action after a complete/stopped receipt.

Verification covers synthetic SDK/real local SQL only: complete 1,003-row history,
eight independent contenders/one provider stub attempt, immutable receipts, ownership
and revocation, invalid/unknown results, cross-request paid holds, lost claim/auth/
stage/application responses, deletion, changed profile/history, exact version replay,
frozen membership and 20-item continuation, six screen recovery cases, no-work-on-mount
and protected API-only cold start. Full catalog restore/rollback and ten intake journeys pass locally (122.59 seconds).
All nine CI jobs passed in run39869071876 (713), with identical head/PR-merge trees.
See buyer-analysis-ci-evidence.json for exact source and job evidence. No production migration or provider call
is authorized or performed by this implementation.

Remaining launch gates include actual provider availability/paid acceptance under
separate scope, current production configuration, full signed-in operator acceptance,
buyer SMS route approval and fresh handset/reply/STOP proof. Manual buyer edits/deletes
remain a separate open review. The exact twenty-migration allowlist is the only
candidate upgrade sequence; every proposal is still unapplied.
