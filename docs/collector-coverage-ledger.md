# Supervised collector coverage ledger

The local preflight now requires a separate coverage ledger whenever `coverage_complete` is true. This is an offline consistency check, not an authenticated reviewer signature, a source-completeness guarantee, a delivery receipt or outreach permission. The Edge ingestion contract is unchanged; a future delivery runner must call preflight and preserve the reviewed evidence before signing/submitting.

```sh
node pipeline/collectors/preflight.mjs manifest.json coverage.json
```

Partial/blocked/failed manifests with `coverage_complete:false` still use the one-file command. Preserve their incomplete collection evidence separately; do not label unknown or unreadable results an empty success.

## Collection procedure

1. Create a run UUID. Set an explicit inclusive filing window of at most 30 days. Select a deterministic source sort and page size. Use filing/recorded dates, not sale dates.
2. Wait for the actual result range/current page and returned rows to settle after each UI action. Typed field values alone do not prove an applied filter.
3. Capture every page, its advertised total, stable document IDs and returned filing dates. Include unresolved notices in the page ledger. Never use a property address or displayed row text as a document ID.
4. Repeat the traversal under identical filters/sort. Both ordered page inventories must match. If counts, IDs, filing dates or order change, retain the interrupted evidence, restart with a new consistent capture, and keep the run incomplete until reconciled. This detects observed drift; it cannot prove the county index itself is complete.
5. Review each individual notice, including every page and the filing stamp. Match county/property identity independently and check current status. Record an explicit included/excluded/unresolved disposition with reviewer, time, evidence URL and explanation. A past sale date does not establish whether a sale occurred. Original loan principal is not current amount owed.
6. Map every included document to its manifest `source_record_id` values; a document may contain multiple properties. Excluded documents have no mapped records. Unresolved documents prevent complete coverage. Every manifest record must map exactly once, with matching filing date and evidence URL.
7. Bind the ledger to the exact manifest run/source/window/records hash. Set `pulled_at` after both traversals and reviews. Run preflight; preserve evidence outside Git. Never copy synthetic fixture attestations into a real ledger.

See `pipeline/fixtures/synthetic-coverage.json` for the complete format. It is test data, not live acceptance. Schema is defined in `pipeline/collectors/coverage.mjs`; unexpected fields fail validation. Each CLI input is limited to 2 MiB. Complete multi-batch reconciliation is not implemented: preflight rejects a complete claim from one fragment. Do not truncate or silently split a source to get around this limit.

## October 13 source findings

- Dallas: pages 1–6 exposed 50 rows each under the September 14–October 13 recorded-date search. By page 7, the advertised total changed from 479 to 490. The pass stopped and cannot establish complete coverage. Relevance was the observed sort; use an explicit stable sort on the next traversal. Bulk export opened a Sign In dialog; it was dismissed, with no account creation or purchase. Public individual previews remain accessible.
- Dallas document `202600002461`, public detail ID `330724568`, exposed 5 pages, recorded September 14 at 12:08 PM and sale date October 6. Only the first preview was inspected; no current-status conclusion or imported lead.
- Collin: direct text filling displayed dates while old rows remained. Selecting September 14 and October 13 through the calendar and waiting for the table produced 164 filtered entries across seven pages (25 × 6 + 14), all returned filing dates within the window. There were 163 distinct displayed row texts; this is not a verified duplicate-document count. Full stable-ID extraction and a matching second traversal remain open.
- Collin detail `4158237` opened publicly and exposed four notice pages plus appraisal context. Its first rendered notice page visibly showed an October 1, 2026 filing stamp, Collin property county and December 1 sale date. The PDF download event and image-download attempt timed out; no downloaded artifact or complete document review is claimed. Original principal must not be used as current debt. Detail URL: https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/4158237 .
- Browser runtime reset during the PDF download wait; in-memory page captures did not become durable manifests. Counts above are investigation evidence only. Capture incrementally to durable local evidence in the next supervised run.

No live manifest passed complete coverage, no records were delivered, and no source schedule was enabled by this work.
