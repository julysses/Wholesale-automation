# Main CSV transaction foundation — October 22

Status: database foundation prepared and verified locally. The application route
is **not yet connected**. R8 and Friday go-live acceptance remain open. No
production migration, runtime, flag, provider or schedule was changed.

## Proposed behavior

`20261022170346_integration_csv_lead_intake.sql` is the thirteenth file in the
explicit forward allowlist. It adds server-only
`public.import_csv_leads(uuid,uuid,jsonb,jsonb)` and private immutable receipts.
The CSV endpoint must supply verified operator identity, a stable request UUID,
normalized/consolidated rows and exact options. A reference can only replay its
original actor, payload and options; a conflicting request fails closed.

One SQL transaction holds a manual-import advisory lock across lookup, lead/list
creation, owner assignment, due follow-up tasks and receipt persistence. It
serializes manual uploads with different references. Each new lead uses the
configured approved `lead_owner_user_id`, not an arbitrary importing operator.
Missing or unapproved configuration refuses new work. Historical exact receipts
remain readable without reassigning work when that configuration changes.

New leads have `ai_calling_paused=true` and both SMS/email sequences false. A CSV
supplies property/owner evidence and grants no outreach permission. Existing leads
retain assignment, DNC, contact attempts, worked status, scores, list membership
and completed tasks. Whitelisted blank fields may be filled; source provenance is
unioned and an additional import note may be appended. Missing source/note input
leaves historical values untouched, including long source text and empty strings.
Existing missing/unapproved ownership is reported for review, not silently changed.

Address matching preserves the Python import contract: full street-suffix tokens,
city and state; cardinal directions and unit distinctions survive. Multiple
existing matches refuse the entire import. The nonunique index avoids deleting or
silently arbitrating historical duplicates. Its immutable SECURITY INVOKER private
normalizer reads no tables. Authenticated writers receive EXECUTE only on that
pure expression so ordinary existing writes can maintain the index. Import RPC,
receipts and scoring intent remain inaccessible to browser roles.

Optional free rules scoring is in the same transaction and only targets untouched,
unscored, unsuppressed records without completed tasks or another CSV AI intent.
It retains the existing SQL scorer, including computed priority/retention metadata
updates. It does not authorize sending. Optional AI intent is saved separately in
`private.csv_import_scoring`; **this checkpoint does not dispatch AI**.

## Verification

`pipeline/integration/verify_csv_import.py` runs against the saved/current-shaped
catalog after the released Facebook delta and all thirteen candidate migrations.
It executes real SQL with service/browser roles and synthetic identities. Coverage:

- 24 address cases match the application helper, including directions, units,
  street suffixes, whitespace and different cities.
- Six new leads have the configured owner, linked due tasks and paused transport;
  a separate importing operator proves assignment follows configured intake owner.
- Exact replay preserves one list/task set; actor, payload and options conflicts
  are refused. Receipts cannot be updated or deleted.
- Worked DNC fields and a completed task survive merging; a no-change import leaves
  the entire row unchanged. Long historical provenance survives absent input.
- A real free-rules score succeeds for a new eligible lead, leaving worked fields
  unchanged. AI intent is durable; overlapping import references do not reserve
  the same record for a second automatic score.
- Invalid later rows, ambiguous historical matches, forbidden fields and invalid
  numeric/options input roll back earlier leads, tasks, lists and receipts.
- Missing/unapproved owner and pending operator fail closed.
- Existing matches beyond 1,000 rows are found in SQL; 501 new rows create 501 tasks.
- Authenticated writes still maintain the index, while import RPC/private receipt
  access are denied.
- Eight sessions are observed waiting simultaneously on the same advisory lock;
  distinct-reference uploads create one property and one task, with seven existing
  results. This does not claim uniqueness across unrelated direct lead writers.

The full rehearsal also compares baseline shapes and authorization, verifies
thirteen-migration apply/full rollback/injected failure rollback and retained
history, then runs land import, pinned-call/SMS contention and ten intake journeys.
All ten journeys passed in 124.92 seconds.
Result: `csv-lead-transaction-result.json` and `production-upgrade-result.json`.
Raw log: ignored `logs/friday-csv-transaction-upgrade-final.log`.

## Required next implementation

1. Add durable AI claim/finish operations before connecting the optional AI import
   path. Claim before any paid request; never dispatch again after an uncertain
   attempt. Validate exact result IDs and scores, compare current records with
   claim snapshots, and hold changed/invalid results for review. Preserve the
   existing optional AI feature rather than silently replacing it with free rules.
2. Replace the old non-atomic `/api/ai/import-master-list` path with this RPC,
   verified Auth actor, correlated receipt validation and explicit unavailable
   behavior if schema is absent. Validate engine values; correct numeric cleaning
   that currently removes minus signs. Keep data-save and scoring outcomes separate.
3. Give Leads, Master List and the standalone modal stable per-upload request IDs,
   explicit same-reference retries and visible pending/review scoring outcomes.
4. Adapt API/UI tests and execute the connected application/SQL path. Keep source,
   DNC, existing workflow and large-file coverage; replace implementation-specific
   batching assertions with actual business outcomes.
5. Review the final exact migration/runtime artifact and rollback boundary; keep
   PR #21 draft until all release requirements and owner acceptance are satisfied.

Current code still uses the old importer. This document and passing foundation
checks must not be presented as completion of main CSV intake or launch readiness.
