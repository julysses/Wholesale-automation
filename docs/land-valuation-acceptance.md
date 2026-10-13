# Land valuation save acceptance

Implemented on the launch-preparation branch and applied to rehearsal only. Production deployment and signed-in acceptance remain open.

## Save contract

- Approved operators use `/api/land-underwriting/valuations/{land_id}`. GET loads the actual saved analysis, selected by creation date/ID, its revision, record count and snapshot hash. Existing duplicate historical records are retained; edits target the selected record.
- A request UUID, exact inputs and expected snapshot hash are saved in session storage before POST. The saved request survives component remount/reconnection in the same browser session. Unconfirmed receipts block new saves; retry uses the original request. A storage failure prevents sending.
- The database locks the land record and selected analysis, compares the full current snapshot, and writes the analysis plus immutable receipt atomically. Competing edits conflict. Replaying an older receipt cannot overwrite a newer revision. A definitive conflict reloads current values for a new human review.
- Snapshot comparison includes the current land record, so a changed property cannot silently accept inputs prepared for the prior record state.
- Server-calculated averages, range and 15% reference use submitted evidence. The client cannot supply derived values, offer prices, MAO, lead stage or approval fields.
- Direct browser insert/update/delete of `land_comps` is disabled. Restrictive policies also prevent older browser clients from bypassing the API. Existing approved read access is retained. Deploy the API and UI together with the reconciled schema; the old direct-write calculator cannot save after this migration.
- Historical comparison-radius metadata is preserved and displayed instead of reset to a default. Historical recommended-offer fields remain unchanged when editing; new records do not populate them. Valuation saves do not update land-lead prices/stages or contact sellers.

## Input behavior

Comparable address and positive sale price are required for every entered row. Entirely blank rows are omitted; incomplete rows produce an error. Up to 50 rows are accepted. Optional area, sale date, distance and source URL remain null when unknown; zero distance remains zero. Source URLs, when supplied, must be HTTPS. Metadata is operator-supplied evidence, not independently verified source data.

Money must be finite, nonnegative, within the storage limit and in cents; sale price and house ARV must be positive. House ARV and an integer comp count must be supplied together. Zero assessed value is valid. Supplied dates must be valid and not in the future; assessment date requires a tax value. At least one valuation input is required. Cleared tax values stay unknown on reopening instead of being repopulated from the lead reference.

Historical blank/zero/malformed metadata may need human correction; it does not become verified evidence through this migration. Multiple legacy records are preserved, not deduplicated automatically.

## Still required before live acceptance

- Signed-in approved-user tests for first save, reopening, competing edits, connection loss and malformed receipts against the intended deployed environment.
- Verify session-expiry/account switching and recovery after browser-session storage is unavailable or cleared. Server receipts survive independently; this UI does not yet provide a receipt-history recovery browser.
- Human review of source quality, comparability, zoning, utilities/buildability and valuation completeness. Saving this form does not complete underwriting.
- Full revision/legacy-record history selection is not implemented in the UI; immutable receipts are retained in SQL, and the current selected record is displayed.
- Coordinated production migration/API/UI release, performance acceptance, and all remaining compliance, provider, collector, scheduler, owner-delivery, buyer-ranking and business go/no-go gates.
