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


## Bulk property queue imported — October 14, 2026

User prioritized scaling beyond the two acceptance examples. Added `pipeline/collectors/foreclosure_property_batch.mjs`: one whole-inventory pass binds original capture/OCR hashes, fresh appraisal situs and exact legal descriptions to saved county records, groups by parcel, reuses known properties and generates both address-only and PropStream Contacts-template CSVs. Full owner names remain intact; no guessed surname or mailing address. All new candidates remain inactive/current_status_review, with full-notice/current-sale and paid tracing holds.

The 164-notice Collin batch produced **75 new property associations**, 84 held notices and 5 reused observations. Saved together in rehearsal via the existing audited identity RPC: **71 new CRM leads plus 4 uniquely matched existing CRM leads reused**. SQL and signed-in Daily Lists confirm **79 associated properties:78 real Collin plus1 synthetic Dallas fixture**, with575unresolved notice observations. This does not mean75fully verified or outreach-ready foreclosures.

PropStream accepted one75-row upload into **WholesaleOS Collin Verification Queue 20261014**, group `https://app.propstream.com/contact/C1239517`; total contacts increased16730→16805 and the selected group visibly loads75rows. No tracing order for this group. Browser file-transfer infrastructure stalled about35minutes before succeeding; the data/import steps themselves are batched. Screenshot: this chat's `outputs/propstream-75-property-batch.jpg`. Private batch queue, legacy matches and atomic SQL remain under `work/verification-20261014/bulk-property-queue/`. Never reimport this accepted group blindly.

The earlier two-property group C1239481 was also accepted. A corresponding provider job **A1902777 / WholesaleOS Collin Trace 20261014** appeared and remains **Processing**, with both expected property rows and no returned contacts. The agent did not click Place Order. Quote was2×12cents; prepaid/total fields were inconsistent. Original requests caf9a39a-1c14-4a27-93b7-a0a4c378dd59 and738f8d8f-d1e1-455a-8b40-2b1f7843850f retain24cents reservation, ledger49.76available. Actual billing is unconfirmed. **Do not reorder, cancel or expire the hold while this provider job exists.** Next immediately reconcile external submission into an audited non-dispatching hold before midnight; then recover original results/billing and CRM follow-up.

Existing-provider whole-contact export did not yield a confirmed file, so reuse checks for the75are incomplete. Next: complete bulk full-notice/current-status corroboration and existing-contact reuse, recover the original two-record processing job, then one only-new eligible batch within the cumulative$50cap. Dallas still201index/address candidates with489full notices uncaptured. Daily scheduler and production remain unchanged; no seller outreach. **149pipeline tests pass**; no frontend change in this update. Unattended launch readiness remains incomplete.


## Original provider results saved and follow-up created — October 14, 2026

The accepted75-row PropStream group C1239517 and79in-app associations remain intact. Implementation9ed11e5 is pushed. The original two-record external job **A1902777** is now **Complete**, with exact source owner/property row IDs4472334311and4472334312 matched to their saved requests. Signed-in Billing History explicitly shows **Skip Trace(2),10/14/2026,$0**. This explains the earlier zero-total quote; do not reorder this completed job.

Added service-only audited `recover_propstream_external_submission`, source migration20261014174808 / rehearsal20261014174948. It adopts an already-visible job into an unknown hold, returnsdispatch:false, preserves original identity/budget, atomically rejects mismatched members and replays immutably. Browser execution/read grants arefalse. Recoverye98b9c02-b5c5-4b24-b320-0b1075e00a27 adopted both original requests without ordering; reconciliation7478aca3-ff1b-49a7-8fe0-a1e8bcd66c19 then saved exact results/confirmedzerocharge.

**8contact records saved** (4phones/4emails across2leads), **2assigned pending high-priority follow-up tasks created**, original requestscompleted, budget **$0actual/$0reserved/$50remaining**. One returned mobile is provider-markedDNC and storedlisted with checked timestamp; all other DNC/channel checks stayunknown. No consent inferred and no outreachsent/authorized. Tasks explain matched-result/channel review and theDNCexclusion. Contacts are provider returns, not independent proof that each channel reaches the owner.

**150pipeline tests pass**, including atomic external-job recovery, mismatched inputs, immutable replay, midnight hold, settlement and denied browser access. Security advisor adds only intentional privateRLS/no-policyINFO; no newWARN. Full private result/billing text, recovery/reconciliationJSONandSQL and screenshots are in this chat'swork/verification-20261014/ andoutputs/propstream-batch-complete.jpg. Never put contacts or billing data in git.

Next: process the75-property verification queue in bulk (full notice/case/current-sale corroboration and existing-provider contact reuse), add a durable unattended worker and accepted scheduling, complete489Dallasfull captures, then trace only new eligible rows as one bounded batch. Bulk import and original2lead-result/CRMfollow-up handoff are accepted; **75are not yet paid-trace or outreach-ready**, and launch is not complete. Production and existing paused daily schedule unchanged.
