# Manual land import production repair — October 22

Status: tested candidate, not deployed. This adds the twelfth proposed feature
migration, `20261022160020_integration_manual_land_import.sql`, after the eleven
previously reviewed feature migrations. The explicit order remains in
`forward-migration-order.json`; never run a directory-wide migration push.

## Defects and resulting behavior

The active Land import parsed the complete CSV but kept only five preview rows,
then inserted that preview into the database. It now retains every row, previews
five, and sends all valid rows through an authenticated receipt API. Zero tax value
remains zero in the preview and storage. Selecting a newer file cannot be undone
by a slower reader callback for the previous file. Labels now say CSV rather than
implying a move from PropStream to XLeads.

`POST /api/land/imports` binds an import UUID and normalized input to the verified
operator. The service-only `import_manual_land_leads` RPC runs the complete batch
in one transaction, serializes manual imports and saves an immutable private
receipt. Exact retries return the saved receipt. A new reference for existing
property addresses preserves all existing work, DNC, owner assignment, contact
fields and pricing. Ambiguous matches or conflicting known parcel/county identity
stop the transaction for review. New land records get the approved importing
operator and an immediate review task; import data never grants contact permission.

The standalone `LeadImportModal` has no current consumer but still contained a
browser insert and background scoring start. It now uses the same server
reconciliation as the mounted Leads/Master List paths, reports confirmed updates
and uncertain outcomes, refreshes caches, and does not auto-retry or start a
separate scoring run. Server scoring is explicitly the existing rules engine.

## Verification

- Four component regressions failed before repair and pass after it. A fifth
  reproduced stale reader replacement and passes after the generation guard.
- Nineteen API checks cover approval/session identity, exact receipt correlation,
  invalid linkage/counts, outreach/work-field refusal and uncertain/conflict outcomes.
- Real PostgreSQL imports six rows and six owned tasks, replays the original receipt,
  deduplicates a new reference, preserves a DNC/under-contract record and completed
  task, rolls back an invalid later row, and rejects parcel conflicts and receipt mutation.
- Eight separate SQL sessions actually overlap: distinct manual import references
  produce one new property and seven existing-property results, with one task.
- Connected FastAPI and actual SQL receipt retry succeeds, using only a synthetic
  Auth identity boundary. No production data or provider calls.
- Twelve-migration apply/full rollback/injected failure, pinned call/SMS checks and
  ten post-upgrade intake journeys pass (123.14 seconds).
- Full backend: 1,288 passed, 10 skipped. Frontend: 245 passed across 52 files using
  `--maxWorkers=4`. Pipeline: 231 passed. Typecheck/build pass; lint has no new
  findings and 143 existing findings. Existing chunk-size warnings remain.

One public-form async render assertion timed out in the initial run while all
suites and PostgreSQL were running in parallel. Its ten-test file passed in
isolation, and the unchanged assertion passed in the full bounded-worker run.
The first SQL harness assertion treated adapter-serialized Decimal zero as an int;
using Decimal comparison corrected that fixture mismatch without changing storage.

Evidence: `manual-land-import-result.json`, `manual-land-import-manifest.json` and
`production-upgrade-result.json`. Local ignored logs begin `friday-import-` and
`friday-production-upgrade-land-import.log`. Reproduce:

```sh
.venv/bin/python scripts/run_offline_tests.py --production-upgrade
.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests -q
.venv/bin/python scripts/run_offline_tests.py npm --prefix frontend test -- --maxWorkers=4
.venv/bin/python scripts/run_offline_tests.py npm --prefix pipeline test
```

## Release and remaining work

Schema must precede the matching runtime. If ported separately, append only the
land-import router registration to production `web/app.py`; do not overwrite the
integration routing wholesale. Preserve private receipts on rollback. The old
runtime has the five-row importer; keep manual imports unused if reverting to it.
This migration changes no historical file, contact setting or scheduler.

R8 is not fully complete. Buyer import and Master List UI coverage remain open.
The main lead CSV reconciliation API still needs proof of concurrent deduplication,
approved ownership and immediate follow-up; source inspection shows no owner/task
creation there. Land list/funnel pagination and error presentation are now corrected and verified;
see `LAND-LIST-COMPLETENESS.md`.
Manual import serialization does not replace the independent county handoff's
identity protocol; cross-feature receiving/reconciliation acceptance remains open.
