# Bulk throughput implementation plan

## Objective

Daily county batches should move from collection to CRM preparation without routine per-property input. Human attention should be limited to unresolved evidence, provider authorization or exceptional results. A completed contact lookup is not foreclosure or outreach clearance.

## What made October 14 slow

- Browser file transfer stalled about 35 minutes for one 75-row upload.
- County notice capture and conservative extraction required development and exception investigation; this was not an accepted daily production run.
- Provider completion/billing and database delivery required ad hoc recovery, with connector/CLI authentication failures.
- Discovery, verification, provider delivery and result handling were mixed into one long interactive session.

## Implemented

- [x] Whole-inventory appraisal matching and property grouping.
- [x] One county current-listing capture matched against the whole property queue.
- [x] Completed-provider result parser with exact identity, duplicate, DNC and warning checks.
- [x] One-command local reconciliation: `npm run bulk:reconcile -- /absolute/private-config.json` from pipeline.
- [x] Stable input-hash batch identity, deterministic output, separate minimal receipt and private CRM package.
- [x] Existing completed jobs retained to prevent repeated tracing, including no-match results.

The private configuration names queue, provider, inventory, day and output paths. The command validates the entire batch before writing output; it accepts 1–500 properties. The private reconciliation package includes follow-up keys, returned contacts, preserved DNC exclusions, current-listing evidence and unresolved checks. It places no order and makes no database writes. Existing 75-row results are already saved in rehearsal; do not import this package again as new work.

Measured October 14: existing 75-row evidence processed in 17 ms locally, reproducing73 matches,2 no-results,473 contact records,145 DNC flags,7 provider warnings and16 current-listing/date matches. This excludes collection, provider upload/processing, database delivery and full foreclosure verification. It is not an end-to-end speed claim.

## Next implementation order

1. **Durable worker and database delivery:** connect this package to an atomic, audited service endpoint. Claim jobs with leases; resume after a crash; retain exact provider receipt and batch identity. Never regenerate a paid order after a timeout. Use supported credentials configured once, not an interactive CLI login each day.
2. **Provider transport:** replace the stalled browser upload path with a supported integration if PropStream grants it, or a reliable bulk file transfer worker. Verify actual account capabilities before promising an API. Keep one job per eligible batch. An existing external job enters reconciliation, never purchase.
3. **Incremental county processing:** discover only new/changed filings, cache original pages and OCR by hash, fetch ownership in bounded batches, and process independent documents with bounded concurrency and retry limits.
4. **Structured verification:** expand notice-format extraction and full legal/owner/case corroboration. Compare current-sale inventories once per source/day. Isolate ambiguous, estate and contradictory records without stopping unrelated records. Unmatched listings are not cancellations.
5. **Operator presentation:** show one batch progress card, stage counts, age and actionable exceptions. Keep ordinary successful stages out of the manual task queue. Create an outreach follow-up only when its required channel checks pass; return contact availability separately.
6. **Scheduling acceptance:** exercise two consecutive runs plus interruption/replay. Then accept the daily schedule and production rollout explicitly. Owner authorized scheduling on October14. Receipt supervision is active every five minutes in rehearsal; source/provider execution remains unimplemented and must not be labeled active collection.

## Acceptance measurements

Record count and elapsed time for discovery, capture, extraction, verification, provider transfer, provider processing and CRM delivery separately. Track records/hour, manual interventions per batch, exception rate, duplicate orders and charge reconciliation. Set an end-to-end service target after measuring the actual source/provider waits; do not promise minutes while those dependencies remain unaccepted.

Required before unattended launch: no duplicate leads, orders or follow-ups on replay; zero extra spend on already completed/no-match jobs; one cumulative $50 cap; billing uncertainty held; no silent truncation; no result marked outreach-ready solely because a phone was returned.

## October 14 scheduled supervision

Added a database-native five-minute supervision function and durable status. It calls the existing list receipt scan without external credentials and creates/reuses an exception task on scanner failure or retention guard. Locks expiry-bearing tables through the check and scan; a failed scanner rolls back its partial changes. No retention deletion, provider call, trace reservation or seller messaging is performed. Service-only execution and private RLS protect status; browser roles cannot invoke the function.158pipeline tests pass. Two live rehearsal runs returned healthy supervision with collection_executed/provider_ordered/outreach_sent all false.

This closes scheduling of receipt supervision, not scheduling of collection or enrichment. The remaining concrete dependency is an unattended runner with supported source/provider transport. Current authorized PropStream access is interactive UI only; a database cron cannot drive that signed-in browser. Do not substitute a timer firing for delivery evidence or invent API availability. Keep missing-source incidents visible in WholesaleOS until actual new daily receipts arrive. Cron setup/inspection/pause SQL is scripts/sql/enable_bulk_supervision.sql; use rehearsal only.

Live acceptance: job2 / wholesaleos-bulk-supervision recorded25automatic successes and0failures during the one-minute acceptance interval, then restored to five minutes. Two initial direct scans also passed. Budget remained$0committed/$50remaining. Existing refresh-lead-retention cron remains inactive. RLS enabled and schema migration20261014200149 registered. Implementation85f34dc passed both GitHub CI runs.
