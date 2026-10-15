# GPT scheduled bulk workflow

Owner instruction, October 15, 2026: GPT owns scheduling and browser work. No separate Mac collector, paid PropStream API, subscription upgrade, or always-running program. Files live in `/Users/juliodominguez/Documents/WholesaleOS/YYYY-MM-DD/`. Retell is a possible future destination, not selected. Export only; no calls/SMS dispatch.

## Execution contract

Existing heartbeat `wholesaleos-dallas-and-collin-collection` is the only county scheduler. Daily 05:00 local Mac time (America/Chicago at setup). Mac must be awake, desktop app running, browser available and signed in. Local folder and browser access must be checked each run; do not promise cloud/offline execution. A scheduled wake is not proof of end-to-end browser acceptance.

1. Read START-HERE-NEXT-CHAT.md and this file. Confirm branch `codex/dallas-collin-launch-prep`, pull before edits, preserve unrelated changes. Rehearsal project `tbhwxgfzbiaqjurghntj` only until production acceptance. Do not change production.
2. Create today's private dated folder. Read prior run receipts and source attempts. Before any county request call `pipeline/collectors/scheduled_batch.py claim --root /Users/juliodominguez/Documents/WholesaleOS/state --county COUNTY --kind foreclosure|tax --day YYYY-MM-DD`. For TAX always add `--legacy '/Users/juliodominguez/Library/Application Support/WholesaleOS/rehearsal-worker/state/worker.sqlite'`. If the old state is missing or unreadable, stop tax collection pending reconciliation. Only `collection_allowed:true` permits collection. Claim consumes the window even on failure/interruption: no blind retries. Daily foreclosure, weekly Monday–Sunday tax maximums.
3. Use accepted county bulk exports/index pages and downloaded notices. Preserve source URL, capture time, official document IDs, file hashes, filing window, pagination and coverage. Reuse cached documents by ID/hash; process batches locally. Avoid property-by-property website lookups. No guessed endpoint, anti-bot workaround, repeated failed request, or full historical recrawl. Dallas tax official ZIP404 remains an exception until an official working link is visible. Review-only tax observations are not verified leads. Missing/partial coverage is not zero new properties.
4. Run existing foreclosure identity/current-sale checks in bulk and deduplicate against live CRM property, owner, source and trace history. Holds remain holds. Completed traces INCLUDING no-results, usable existing contacts, submitted/reserved/uncertain orders must never be re-ordered. Original A1902777 and 75-row A1903016 are completed; reuse them. Prior 75 have only16 current-listing matches, not full verification.
5. Save master Excel with sources, stable IDs, statuses and exceptions. Use spreadsheet skill and bundled artifact runtime; no need to launch Excel itself. Save separate provider upload CSV using the exact current visible PropStream import mapping. Existing accepted header evidence is `work/verification-20261014/propstream-verified-batch.csv` in the October13 chat workspace. Do not upload the master multi-sheet workbook blindly or presume a WholesaleOS CSV import contract; use its accepted bulk ingestion/receipt path.
6. Import genuinely new verified properties into rehearsal WholesaleOS through the accepted ingestion interface. Confirm durable receipt and assigned high-priority follow-up. Existing county-property notification trigger produces/updates the daily app notification. Verify it; do not fabricate a notification for an unconfirmed or replayed import. GPT reports new-property count and awaiting-trace count only after receipts prove those states.
7. Upload only new verified eligible rows through signed-in PropStream browser UI. Verify row count/mapping, preserve group ID, exact quote and eligibility snapshot. Before final skip-trace order, obtain existing durable CRM reservation against the cumulative5000-cent budget, including actual spend, reservations and uncertain orders. Never use a workbook total as the budget authority. No reload, card fallback, Connect trial, upgrade or paid API. Unknown price/reservation/provider outcome stops submission. Save provider confirmation/job ID; never retry an ambiguous order.
8. Check previous pending jobs once per scheduled run, rather than polling continuously. When complete, download the provider result, reconcile all rows with `propstream_result_batch.mjs`/`bulk_reconcile.mjs`, save contact flags and settle existing reservations through accepted CRM receipt operations. Do not equate a download click with a saved file; verify path, bytes, row count and receipt. Browser download failures become exceptions without security workarounds.
9. Prepare separate call and SMS files only after current suppression and channel eligibility evidence is available. Exclude DNC-listed AND unknown/unrecognized DNC from campaign files. Preserve provider warning/estate/wrong-party holds. Recheck suppression at actual export/use; absence of a PropStream DNC badge is unknown. SMS requires existing documented consent and app eligibility checks. Phone discovery is not consent. Do not label review contacts campaign-ready. No transfer to Retell or another dialer until the destination is selected.
10. Record run counts, source coverage, input/output hashes, CRM/provider receipts, budget, exceptions and exact next step locally. Update progress docs with non-PII summary and commit/push logical changes. Never commit contacts, workbooks or credentials. Notify only new properties/awaiting tracing, completed handoff, failure or required action. Stay quiet on unchanged non-actionable runs. No new fake property to test notifications.

## Implemented local preparation

`scheduled_batch.py claim` is an atomic SQLite gate. Parallel claims cannot both win. Legacy failed tax attempts consume the current week. It does not collect, send, sleep, schedule or authorize spend.

`scheduled_batch.py package-completed --source RECONCILIATION_JSON --root /Users/juliodominguez/Documents/WholesaleOS --day YYYY-MM-DD` builds a stable, source-hashed dated packet, workbook input, contact holds and header-only campaign CSVs. It rejects re-order/outreach-authorized input. DNC-listed/unknown phone records are excluded and masked to last four in Excel. The current implementation deliberately has no automatic campaign-clearance writer: both channel files stay empty until authoritative clearance is integrated.

`scripts/build_scheduled_workbook.mjs INPUT_JSON OUTPUT_XLSX` creates the Excel and previews using the bundled `@oai/artifact-tool`. Copy this builder to a private run folder with a `node_modules` symlink to the dependency-loader location. Use the skill's artifact-start marker, inspect every sheet preview, and verify output. These programs run only during GPT work, not as background services.

## Acceptance and remaining work

- [x] Atomic daily/weekly request gate and legacy attempt preservation, tests pass.
- [x] Dated completed-batch packet and Excel builder implemented.
- [x] Existing75 saved as a completed baseline, never presented as new leads.
- [ ] First scheduled unattended wake proves browser and local folder access.
- [ ] Fresh full foreclosure collection, verification and genuinely new CRM delivery.
- [ ] New eligible batch reaches PropStream with durable reservation and provider receipt.
- [ ] Provider download saves and matches without manual intervention.
- [ ] Current DNC/channel clearance produces nonempty eligible call/SMS exports.
- [ ] Production acceptance and promotion.

The schedule is an agent workflow with exception handling, not a proven unattended transport. No promise that all sources expose a one-request bulk download.
