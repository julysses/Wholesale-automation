# Supervised foreclosure inventory capture

This is the repeatable **index discovery → review queue** procedure. It does not complete notice extraction, independent property identity, current sale status, or an unattended collector. Keep `status:partial` and `coverage_complete:false` until all document-review gates pass. Never treat a displayed address as a unique property or infer a completed sale from its date.

## Browser capture

Use the approved computer-use surface, with incremental private evidence saves. Do not access hidden browser state or replay undocumented network requests. Stop at access restrictions. No county document purchase is authorized.

Dallas: use the official county-linked `https://dallas.tx.publicsearch.us/`, Department Foreclosures, Advanced Search, Recorded Date Range, and clear sale-date filters. Select Document Number ascending and250rows/page. Save each displayed result range, capture timestamp and row's visible cells plus its `Document <id>, not selected, checkbox` label. Repeat the entire traversal, preserving each page in order. Saved capture format is `{source: <observed results URL>, passes: [[{status, at, rows:[{cells, id}]}], [...]]}`. The adapter validates the source URL, displayed date range, document layout and pagination rather than guessing column positions after layout changes.

Collin: open `https://apps2.collincountytx.gov/ForeclosureNotices/`. Set Filed Date Start/End through the calendar controls; direct textbox filling can leave old results on screen. Verify the applied dates, filtered total and in-window returned dates. Preserve Address sort and25rows/page. Wait for `Current page N`, not just the clicked `Page N` control. Capture each row's rendered text. Click its address/title paragraph to open the public detail tab. Wait for its matching heading, save the visible detail snapshot and exact `/DetailPage/<id>` URL, then close that detail tab. Keep the search tab on the same filtered page. If a popup is still loading, inspect its actual state and resume that row; do not skip or guess an ID. Repeat all pages a second time.

Collin input shape:

```json
{
  "source": "https://apps2.collincountytx.gov/ForeclosureNotices/",
  "window_start": "2026-09-14", "window_end": "2026-10-13",
  "page_size": 25, "total": 164,
  "passes": [
    [{"page": 1, "row": 0, "text": "<visible row text>", "url": "<observed detail URL>", "captured_at": "<actual UTC timestamp>"}],
    [{"page": 1, "row": 0, "text": "<second observation>", "url": "<observed detail URL>", "captured_at": "<actual UTC timestamp>"}]
  ]
}
```

Each pass above must contain **every** row, ordered by page and zero-based row. The abbreviated example is not a deliverable manifest. Preserve advertised totals and applied-filter screenshots/snapshots beside the capture. Duplicate displayed text may represent different notices: October13's164entries had164distinct detail IDs, although only163distinct displayed texts.

## Validate, generate, and deliver

```sh
node pipeline/collectors/foreclosure_inventory.mjs capture.json new-private-manifest-directory --dallas-visible
# or --collin-visible
python3 pipeline/collectors/deliver_keychain.py /absolute/path/to/new-private-manifest-directory
```

The converter requires two matching inventories captured within24hours, stable IDs/URLs, contiguous pages, an inclusive filing window no longer than30days, and valid dates. It generates bounded500record batches and saves the normalized evidence. It refuses an existing output directory; after any delivery uncertainty replay that existing directory instead of regenerating a run. Both supported sources use scoped rehearsal Keychain credentials. Delivery journal and raw county evidence stay outside Git.

Index addresses remain `raw.indexed_address`; situs street/city/ZIP/parcel/owner/debt are null. All records require notice/identity/current-status review. A notice describing several properties must be extracted into independently reviewed property records before association; do not pick the first address. Source IDs survive repeated observations so eventual CRM reconciliation can reuse the same property and prevent retracing. Ingress acceptance is not a lead count or contact permission.

## October13 acceptance

- Dallas: two250+240page captures,490stable IDs. Run `db1c2221-ed79-4ece-bf12-386a84d59477`, accepted490records, zero property associations.
- Collin: two seven-page captures,164stable IDs. Run `a0c09287-a888-4e8e-97ea-ab4964e5ab69`, accepted164records, zero property associations. Includes notice4158237 previously delivered separately with all-page review; that earlier record is an additional observation, not another notice/opportunity.
- Both remain partial. Full notice extraction, five clean supervised runs and14unattended days remain unfulfilled. No paid traces, messages or production changes.
