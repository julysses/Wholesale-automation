# Connected main CSV intake — October 22

Status: candidate API/UI and database transaction connected and verified locally.
No production migration, runtime, flag, provider or schedule was changed. R8,
operator acceptance and Friday go-live certification remain open.

## Behavior

`20261022170346_integration_csv_lead_intake.sql` remains the thirteenth file in the
explicit forward allowlist. It has not been applied in production. Its current
hash supersedes the earlier foundation-only checkpoint. It now provides:

- `public.import_csv_leads(uuid,uuid,jsonb,jsonb)`: atomic lead/list save, approved
  configured intake owner, linked due tasks, free rules scoring and immutable receipt.
- `public.claim_csv_import_scoring(uuid,uuid,uuid)`: one-way optional AI claim,
  committed before any model request, with current snapshots and untouched-work checks.
- `public.finish_csv_import_scoring(uuid,uuid,uuid,jsonb)`: exact claimed IDs and
  scores, snapshot comparison, preserved human work and durable completion/review.

All business RPCs and private receipt/operation tables are server-only. The only
new authenticated callable is the immutable SECURITY INVOKER private address
normalizer needed to maintain the functional index. It reads no business data.
Actual authenticated inserts still work; browser import/receipt access is denied.

`POST /api/ai/import-master-list` obtains operator identity from verified Auth,
normalizes/consolidates all rows and validates the correlated SQL receipt before
reporting success or dispatching a model. It never falls back to non-atomic table
writes if schema is absent. Legacy callers without a UUID get deterministic
identity from actor, normalized rows and options. Modern callers retain an explicit
UUID for each prepared upload. Actor/payload/options conflicts are refused.

Numeric validation preserves minus signs and rejects negatives, booleans,
malformed values, unsupported precision/range and invalid state codes before any
RPC. The Leads mapper sends numeric source text unchanged for this validation.
An invalid later SQL row rolls back the entire data transaction.

A manual-import advisory lock serializes different references through indexed
lookup, lead creation, due tasks and receipt persistence. Matching keeps the
existing Python street-suffix/city/state contract, preserving directions, units
and different cities. Ambiguous historical matches refuse the whole import;
legacy duplicates are not deleted. This proves manual-upload serialization, not
uniqueness across every unrelated direct lead writer.

New leads use configured approved `lead_owner_user_id`, not an arbitrary importing
operator. Missing/unapproved configuration refuses new work. They have calling
paused and SMS/email sequences false; CSV grants no contact permission. Existing
assignment, DNC, contact attempts, worked status, scores, list membership and
completed tasks survive. Only blank whitelisted fields may be filled; provenance
may be unioned and an import note appended. Absent source/note input does not
truncate long history, clear empty strings or update an unchanged record.
Existing ownership gaps are reported for review rather than reassigned silently.

Default free scoring occurs in the same transaction and only targets untouched,
unscored, unsuppressed records without completed tasks or an existing CSV AI intent.
The existing rules scorer may refresh computed priority/retention metadata; it
never authorizes outreach. Master List now uses this transaction and no longer
starts a separate global background scoring run after save.

Optional AI intent reserves eligible records across later import references. A
claim locks its operation and lead/task records, captures snapshots and changes to
`submitting` before returning dispatch authority. Only the first caller receives
that authority. Even replaying the same claim UUID does not grant another dispatch.
The SDK uses `max_retries=0` for this CSV path; each batch must return the exact
claimed IDs, complete output and valid 1–3 integer scores. The SQL finish also
validates tiers/fields and checks snapshots. Changed records/completed tasks are
held, not overwritten. Invalid/partial/foreign results hold the entire attempt.
A timeout records review when possible; an uncertain claim/result stays held or
submitting and is never automatically dispatched again. Terminal exact-result
replay returns the saved result; conflicting results are refused.

Saved-data outcome and scoring outcome are separate. Scoring review/uncertainty
returns confirmed save counts with a warning. Leads and the standalone modal offer
explicit same-body retry after an uncertain data response. All three callers
validate request identity/counts/state. Master List retains its UUID and list name
in its existing SPA store across route remounts; a full page reload still loses
that store. New references still deduplicate properties and cannot automatically
reserve the same record for another CSV AI attempt.

## Verification

Backend: **1,325 passed, 10 skipped**. Frontend: **262 tests across 54 files passed**
with four workers. Typecheck/production build pass. Lint gate adds no findings;
143 existing findings remain. Existing build chunk-size warning remains. Pipeline
source is unchanged from its prior 231-test checkpoint.

The final disposable PostgreSQL run restores the saved/current-shaped catalog and
released Facebook delta, compares shape/access, verifies all thirteen candidate
migrations, full/injected failure rollback and retained history, then exercises:

- 24 normalization cases; configured owner with a different importing operator;
  linked due tasks; exact receipt replay and actor/payload/options refusal.
- Worked/DNC fields, completed tasks, long provenance and unchanged rows preserved;
  invalid whole-batch rollback; ambiguous identity and owner setup refusal.
- Existing lookup beyond 1,000 records and 501-row/501-task creation.
- Eight observed concurrent manual uploads: one property/task plus seven existing.
- Connected FastAPI → real SQL with only Auth/model boundaries stubbed: existing
  source/phone reconciliation, a new owned task, qualification and exact retry.
- Provider timeout: one model attempt, saved data confirmed, review and no replay.
- Commit-then-lost-ack at data save, claim and result: exact data reconciliation,
  zero model attempts after lost claim response, one attempt after lost result.
- Invalid/missing/foreign IDs, boolean/out-of-range scores, forged tier/fields,
  changed human work and completed tasks held without unsafe scoring writes.
- Eight sessions observed contending for one scoring row: one dispatch winner;
  eight parallel exact finishes return the same persisted result.
- Existing manual land import and pinned-call/SMS overlap; ten intake journeys
  pass in **125.82 seconds**. No provider calls or production rows copied.

HTTP receipt tests replace old fake-table batching/page assertions; persistence
and historical preservation now run on real SQL. The old “missing list schema
still imports” expectation was deliberately replaced with fail-closed missing-RPC
coverage; safe schema-before-runtime ordering is required. Component tests cover
all rows, exact explicit retry, wrong-reference refusal, warning vs save outcome,
Master List remount recovery and no background score start. SDK parser tests prove
no automatic retries and reject incomplete/mismatched results.

Evidence: `csv-lead-transaction-result.json`, `csv-connected-scoring-result.json`,
`csv-lead-transaction-manifest.json`, `production-upgrade-result.json`. Raw logs are
ignored `logs/friday-csv-*`. These checks do not prove production Auth/JWT behavior,
real-browser operator acceptance, live carrier/inbox delivery or production-volume
lock/execution time.

## Remaining launch work

1. Review import history/ownership and scoring-review recovery in the signed-in
   operator walkthrough. Verify real runtime duration for large optional AI uploads;
   current synchronous multi-batch behavior and production-scale partial-batch
   recovery are unproven. Do not certify that path from small synthetic examples.
2. Finish buyer workflow UI coverage, remaining R1–R12 business acceptance and
   dependency/security review. Complete land visibility proof remains separate.
3. Review the exact schema/runtime release artifact, index lock exposure, recovery
   boundary and deployed ordering. Preserve all immutable receipts/tasks; do not
   drop evidence as runtime rollback. Do not apply the migration directory wholesale.
4. Verify actual Meta/website consent/routing, effective sending flags and scoped
   provider/owner delivery, reply and STOP acceptance with the confirmed fresh
   destination. Keep broad schedules paused pending owner review.

PR #21 remains draft. Local green checks do not authorize deployment or activation.
