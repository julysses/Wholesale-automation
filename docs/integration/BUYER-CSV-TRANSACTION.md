# Buyer CSV: committed data, immutable recovery and protected consent

October 22, 2026. Draft candidate only. Nothing applied to production. The explicit
forward allowlist now contains fourteen proposals; the additional migration is
`20261022190018_integration_buyer_csv_transaction.sql`, created with Supabase CLI.
Apply reviewed schema before its matching API; missing RPCs fail closed.

## Problem and resulting behavior

The previous endpoint returned `processing` before a background task persisted
anything. Individual buyers/transactions could fail while the import log was marked
complete. Catch-all insert fallbacks could duplicate committed records after a lost
response. Parser output also granted consent from contact presence, reactivated
existing buyers and overwrote saved preferences/scores through a broad update.

The API now parses the complete bounded file and saves buyer groups, transactions,
completed import log and private receipt in one SQL transaction. It acknowledges
`complete` only after validating the correlated committed receipt. There is no
untracked insert fallback or background persistence/scoring after acknowledgment.
New buyers retain deterministic parser scores; existing buyer scores/classification
are preserved and may require a separately reviewed explicit rescore.

The browser carries a stable import UUID through explicit retries. A failed or
uncorrelated response stays unconfirmed, keeps its file/reference and cannot appear
as success. Closing an uncertain modal preserves its recovery state while the
component remains mounted. A refresh callback failure cannot turn a confirmed save
into another write. Legacy callers without a UUID receive a deterministic reference
from verified operator plus source/options fingerprint. Exact reference replay
returns immutable original counts; changed input or another actor is refused.

## Data protection and identity

- Uploaded phones/emails never imply opt-in. New buyer SMS/email flags are false.
  Existing consent, inactive status, buy box, land preferences, notes, custom tags,
  scores, classification and history survive. Blank contacts with an already-true
  opt-in flag are not rebound to imported destinations.
- Entity/contact matches must agree. Multiple identities, a shared contact attached
  to another identity, or an existing same-name contactless person require review.
  Distinct groups cannot resolve to the same buyer in one batch. No arbitrary
  `limit(1)` identity choice is made.
- Matching existing purchase events are counted, never overwritten. Conflicting
  history or ambiguous existing duplicates reject the entire batch. The production
  APN-per-buyer unique index is preserved: different events on the same parcel
  require review instead of silent replacement. This limitation remains open for
  source/operator acceptance; it is not event-level deduplication certification.
- Duplicate source purchases do not inflate a new buyer's initial signals. Missing
  financing details are not cash evidence. Malformed/negative purchase prices are
  rejected rather than converted to positive values. Invalid CSV rows reject the
  batch; explicit cash/entity/price filters remain intentional skips.
- UTF-8 files are bounded at 4 MB and 5,000 source rows, with explicit refusal above
  either boundary. Accepted rows are not truncated to the five-row preview.

## Access and locks

The receipt table is private, RLS-enabled, SELECT/INSERT-only for service_role and
protected against UPDATE/DELETE. The RPC is SECURITY INVOKER with an empty search
path, denied to PUBLIC/anon/authenticated and granted only to service_role. The API
uses verified request identity; SQL rechecks an approved profile and receipt owner.

Import-reference advisory locks serialize exact retries. Bounded table write locks
on buyers and purchase history protect identity decisions against both import and
browser writes. Lock acquisition times out after three seconds. This is a deliberate
tradeoff pending production-volume/lock review, not proof of low impact at maximum
volume. No production table or index changed during development.

## Local evidence

- Backend: 1,345 passed, 10 skipped. Frontend: 295 tests in 59 files passed.
- Pipeline: 231 passed. Typecheck/build passed. Lint gate has no new findings;
  142 existing findings remain. Existing large-bundle warning remains.
- Real API/PostgreSQL checks prove same-reference replay, changed-reference/foreign
  actor refusal, full rollback after an earlier valid group, commit-then-lost-response
  recovery, preserved buyer controls, guarded blank consented contacts, same-name
  review and duplicate-purchase signal preservation. Auth uses a local stub.
- One complete file saves all 1,003 purchase rows. A 5,001-row file is refused before
  writes. Four database sessions start behind a barrier and import the same new
  entity under different references: one buyer and two purchases are created.
- Frontend checks confirm completed counts, lost-response retry with identical
  file/reference, rejection of queued/wrong-reference/partial receipts and safe
  refresh callback failure. No real provider/model calls.
- Full fourteen-migration upgrade, historical retention/access, full/injected-failure
  rollback, CSV/land import/scoring, buyer complete reads, pinned-call/SMS contention
  and ten intake journeys are recorded in the final upgrade result and logs.

Sources: `buyer-csv-transaction-manifest.json`, `production-upgrade-result.json`,
`pipeline/integration/verify_buyer_import.py`, and ignored
`logs/friday-buyer-import-{backend,frontend,pipeline,build,lint,upgrade-final}.log`.
Supabase function/transaction/privilege guidance was reviewed at
https://supabase.com/docs/guides/database/functions; local role/ACL assertions apply
here, rather than claiming a production advisor scan proves an unapplied proposal.

## Remaining launch gates

Production-volume/max-file latency and lock acceptance, event-level APN/reacquisition
review, signed-in browser recovery across reload/exit, manual buyer-create lost
responses, durable explicit classification/rescoring and complete outreach history
remain open. Reimport recovery does not solve arbitrary manual CRUD ambiguity.
Fresh live consent/routing, runtime flags, owner notification, handset delivery,
reply/STOP, broader dependency/security and exact release/rollback approval remain
required. Broad schedules stay paused; do not replay held sessions or clear DNC.
