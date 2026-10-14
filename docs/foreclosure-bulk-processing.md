# Bulk foreclosure processing

The daily operating unit is a county batch. WholesaleOS shows completed stages, exceptions, the remaining tracing allowance and CRM follow-up actions. Routine property entry, CSV uploads and quote forms are not part of the operator page.

## Flow and acceptance

1. Capture the county index with stable filing identities. Fetch all pages of new notices; reuse hash-checked saved pages and OCR. Dallas capture reliability remains unfinished.
2. Read official appraisal ownership data in batches. Collin's [official portal](https://collincad.org/open-data-portal/) links the daily [Owner Prop List](https://data.texas.gov/d/ahis-pci3). The public SODA2 export endpoint and its field definitions were verified in the portal. Query only county-linked parcel IDs, up to100per request. Preserve every owner row; stop on redirects, schema changes or potentially truncated results. Dallas's [official Data Products page](https://www.dallascad.org/DataProducts.aspx) links the current2027ownershipZIP. The offline index-matching adapter is exercised; unattended download freshness and complete-notice corroboration remain open.
3. Match the county property's situs to fresh appraisal situs. Never substitute the owner's mailing address. Retain units, city and postal code; mismatch, missing parcels, stale data and co-ownership become exceptions. OCR text and saved county metadata must match their original page/HTML hashes.
4. Group matched notices by county and parcel. Preserve distinct liens/cases and every filing observation. Only an exact extracted trustee-case ID and sale date can suggest a repeat-case group. Do not repair unreadable identifiers by guessing or merge different liens.
5. Finish structured notice, owner/legal and current-sale verification in bulk. A matching address or future indexed date does not verify an active foreclosure. The current conservative extractor cannot yet clear most notices; improve extraction/corroboration rather than turn this queue into hundreds of manual entry tasks.
6. Reuse CRM/PropStream contacts, exclude suppressed, previously enriched and uncertain requests, then build one new-eligible PropStream batch. Signed-in provider UI remains the supported handoff. Acquire the actual quote and prepaid balance; reserve/claim before ordering. Total spend plus outstanding commitments must stay within the single$50allowance. Do not refill or enable recurring purchases.
7. Reconcile original provider results/receipt/actual charge using exact owner and property identity. Retain ambiguous/absent rows as exceptions. Save contact evidence and one owner-assigned high-priority CRM follow-up. Automated outreach requires its separate channel checks; skip tracing never creates consent.

## Implemented and exercised October14

`pipeline/collectors/foreclosure_batch.mjs owners <details.json> <private-output>` fetched101distinct Collin parcels in2public requests. All101rows carried a2026-10-14data date. Original receipts/rows remain private.

`foreclosure_batch.mjs assess <captures-root> <capture-manifest> <details.json> <ocr-root> <owners/snapshot.json> <private-output> YYYY-MM-DD` processes the entire captured county inventory offline. Node plus Python3 are required. It uses the existing county HTML parser to bind metadata to original bytes; it never calls a paid model or writes contacts. Each run writes private `report.json` and a minimal, hash-bound `receipt.json`. No names, mailing addresses or full scan text enter the app receipt.

The164-notice Collin batch matched103notice addresses to fresh appraisal data and produced162property/unresolved-notice groups.21notices had exact full situs support in OCR;162had extraction/matching exceptions and2passed the initial triage checks. **Zero tracing eligibility was granted by this processor.** Case-number OCR errors remain held, even for a property independently reviewed earlier. These counts describe the saved inventory, not county-wide coverage or launch acceptance.

`save_foreclosure_batch` accepts1–500notices atomically, requires existing complete capture and extraction receipts, recomputes counts, rejects eligibility claims and preserves immutable batch identity. Reuse the exact saved UUID/receipt on delivery uncertainty. A new processing result needs a new saved UUID. Browser roles cannot read or write the private table. Capture status supplies the latest batch to Daily Lists and flags changed capture evidence.

## Remaining launch gates

- Broader structured extraction and legal/owner/current-sale corroboration, including missing parcel IDs and low-quality text.
- Complete Dallas acquisition and full-notice corroboration; the bulk appraisal index-discovery adapter is exercised.
- Actual eligible PropStream batch quote/order/result/charge and CRM follow-up acceptance; currently$0spent. A two-property acceptance file is prepared privately, but the browser upload did not select it; enable the ChatGPT extension file-URL setting before retrying. No provider import/order was submitted.
- Reliable unattended county/provider worker, daily scheduling acceptance and remaining security/operator checks. Scheduling stays paused; production and seller outreach remain unchanged.

## Dallas index-discovery adapter

`dallas_appraisal_batch.py <archive.zip> <download-receipt.json> <saved-index-batch.json> <private-output> YYYY-MM-DD` reads ACCOUNT_INFO and MULTI_OWNER directly from the official ZIP without extracting archive paths. It requires the original ZIP hash, fresh source-as-of evidence, saved index hash, reviewed table headers and declared appraisal year. It scans the full archive once for the complete notice batch, preserving units and ambiguities. Official source includes literalplus signs in some account IDs; preserve them. It writes private reports plus minimal in-app receipts containing only document identities/counts.

October14run:863253accounts,490index notices,201single-account situs matches and289matching exceptions. The index-to-appraisal stage appears separately from completed-page verification. It grants no tracing eligibility; full Dallas acquisition remains incomplete. `save_foreclosure_appraisal_batch` binds the exact saved county run/batch/records hash and all document IDs, calculates totals, rejects verification/outreach claims, and atomically replays immutable batch IDs.
