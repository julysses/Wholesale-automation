# Foreclosure priority list → PropStream → outreach → follow-up

## In-app extraction receipts — October 13, 2026

Rehearsal now durably stores **425 extraction receipts:420 Collin pages/164documents and5Dallas pages/1document**. Live SQL confirms67Collin and2Dallas text-quality review pages, with verification_granted:false. Full OCR text/blocks remain in private local evidence files; the database validates the supplied text hash and stores only page/source linkage, text hash/length, engine, confidence, quality flag and timestamps. It does not copy the full text into another retention store.

Added private RLS table `wholesale_ingest.foreclosure_extractions`, service-only SECURITY INVOKER `save_foreclosure_extractions`, and extraction counts on the existing approved-admin capture-status API. Complete capture/page hashes must match; text hashes, input bounds, timestamp, immutable replay and atomic batches are enforced. New snapshot captures do not inherit old extraction credit. No lead/signal/contact/follow-up mutation. Live browser-role read/write/execute grants are false; server execute true. Rehearsal migration20261014022100 corresponds to source20261014021657_foreclosure_extraction_receipts.sql. Production unchanged.

`extraction_receipt_manifest.py` builds private uploads from hash-bound OCR/capture receipts and rejects invented verification claims. Seven Python tests, two database integration tests, three frontend tests, build and lint check pass (146existing lint findings; existing bundle warning). Security advisor's new table INFO is intentional RLS with no browser policies; pre-existing auth/definer warnings remain. Daily Lists now includes extracted-page/document counts and text-quality exceptions without entry forms; deployment/browser acceptance is pending this push.

Resume with latest preview acceptance, structured property extraction and page-specific evidence, independent property/current-sale verification, remaining489Dallas full notices, then only-new PropStream reuse/trace/result reconciliation and CRM follow-up. No new eligibility, trace order, spend, seller message, schedule activation or production promotion. All local extraction processes finished.


## Bulk local OCR accepted — October 13, 2026

**Collin:420/420 pages across164 documents extracted; Dallas:5/5 pages for notice330724568 extracted. Zero processing failures and zero empty-text pages.** Collin67pages across52documents and Dallas2pages were flagged below85confidence. OCR occasionally logged an unrecognized tiny line; page success is not a claim that every character was read. No identity/current-status/tracing eligibility was granted.

Implemented `pipeline/collectors/notice_ocr.mjs` using pinned Tesseract.js7.0.0 and local English package1.0.0. Installation used npm with scripts disabled; audit reported zero vulnerabilities. This worker ran successfully **inside the normal sandbox**, with local image bytes and local language data, no paid model API or document transmission. The earlier native Vision outside-sandbox request remains declined and was not retried. Two OCR tests plus four county viewer tests pass; inputs are county/identity/hash checked, complete-page-only; page outputs are private, atomic and resumable with image/text hashes and explicit verified:false/trace_eligible:false. See `docs/county-notice-ocr.md`.

Private evidence under this chat's `work/county-sources/collin-ocr/` and `dallas-ocr/`; full capture roots are the sibling `*-bulk-details/` directories. Existing capture manifests remain in `work/capture-receipts.json` and `work/dallas-capture-receipts.json`. A full Collin replay verified420cached outputs without repeating recognition. OCR is not yet stored or displayed in the app; only capture receipts are. Live Daily Lists confirms Collin164complete/420pages and Dallas1complete/5pages. PropStream signed-in Contacts was revalidated (existing historical contacts present), import dialog canceled with no upload/order/spend.

Next: structured extraction with page-specific evidence and quality exceptions, durable in-app extraction/verification statuses, independent property/current-sale corroboration, remaining489Dallas notices, then only-new PropStream batch/result/charge and follow-up acceptance. A direct public Collin CAD request returned403; do not use that HTTP route as an accepted collector or work around restrictions. Supported browser verification remains available. No trace spend, seller outreach, schedule activation or production changes. Local OCR processes are finished.


## Dallas capture support — October 13, 2026

Added Dallas PNG support to the county capture manifest validator, with explicit county selection, image signatures, expected-page bounds and existing identity/hash checks. Six Python tests pass, including wrong-county, tampered-file, duplicate-page and incomplete-manifest rejection. All164 Collin captures previously accepted remain unchanged.

Dallas notice330724568 now has five distinct original PNG pages saved privately in `work/county-sources/dallas-bulk-details/330724568/`. Rendered county Summary HTML is the receipt's hashed `detail.html`; no signed download URLs are persisted in its receipt. The existing rehearsal service function accepted the capture and live SQL confirms Dallas1complete/5pages plus Collin164complete/420pages. This Dallas sale date is past; no eligibility granted. Remaining489 Dallas full-notice captures are unfinished.

The Dallas viewer's page counter advances before its image changes. Never accept counter-only traversal as page evidence. The pageAssets inventory retained all five document-specific numbered assets, which were downloaded and checked for contiguous page numbers and distinct hashes. Downloads were extremely slow: approximately144seconds for page1 and668seconds for the remaining4; this is a bulk launch bottleneck. Do not repeat large downloads without a bounded, recoverable collection strategy. Current OCR extraction remains unfinished; a sandbox-compatible local OCR option is being investigated. No trace spend/outreach/production change.


## Collin full-page capture accepted — October 13, 2026

All **164 Collin notices /420 expected pages** now have complete, hash-checked local page sets. Four transient viewer failures were recovered through the visible viewer; no incomplete notices remain in this saved inventory. The private capture manifest passed all identity/file-hash checks and was replayed through the existing service-only receipt function in rehearsal `tbhwxgfzbiaqjurghntj`. Live SQL and the deployed Daily Lists page both confirmed **164 complete documents,420/420 pages**. Screenshot: this chat's `outputs/wholesaleos-daily-pipeline.jpg`. Latest capture UI deployment285a375 is accepted; no manual input controls were introduced.

This completes document acquisition for the saved Collin index inventory, not content extraction, current-sale verification, county-wide completeness, or tracing eligibility. Dallas still has490 index records and zero saved full-notice capture receipts. Next: bulk content extraction and independent property/current-sale corroboration, Dallas full-notice acquisition, durable verified candidates, then the actual PropStream eligible-batch handoff and CRM follow-up. The Vision escalation remains declined; do not repeat it. No trace orders, spend, seller outreach, schedule activation or production changes. $50 total authorization remains unspent.


## Current checkpoint — in-app capture receipts, October 13, 2026

Rehearsal now stores capture receipts for all164 Collin notices: **276/420 pages,88 complete documents**. Includes single-page notices already complete from their initial captures.69 notices have separate all-pages traversal receipts (inventory offsets0–67 plus4158245);76 notices still lack complete page sets. Next bulk traversal offset68; prefer receipt/hash resume to fixed offsets. No document has been newly certified as identity/current-status verified, and no trace purchase or outreach occurred.

Added private `wholesale_ingest.foreclosure_captures` and service-only, SECURITY INVOKER save/status functions. Batch save binds to existing ingested notices, checks official URL/IDs, hashes, ordered unique pages and timestamp, rejects conflicts, preserves richer receipts on partial replay, and is atomic. No lead or eligibility mutation. Browser roles have no direct read/write grants; server status validates the approved session administrator. Rehearsal migration is20261014012158; source migration20261014011940_foreclosure_capture_receipts.sql. Production untouched.

`capture_receipt_manifest.py` validates saved HTML/page files before producing the private upload manifest. MCP mutation calls repeatedly failed with catalog-change errors; read-only queries and migration worked. Authenticated CLI fallback succeeded: `supabase db query --linked --project-ref tbhwxgfzbiaqjurghntj --file <private SQL>`. Do not omit --linked or use an implicit project. The upload remains idempotent. CLI returned the counts above; live grants were verified.

Daily Lists adds a no-input County document capture section through GET /api/operations/lists/captures. Frontend build and3 component tests pass;10 API tests pass; capture database test passes (atomicity, conflict/replay/access controls);4 viewer tests pass including late observation recovery. Lint has no new findings (146 baseline). Security advisor: new private table has intentional RLS/no browser policies; remaining auth/definer warnings are pre-existing launch items, not cleared by this update. UI deployment/browser acceptance of this newest section is pending push.

Continue remaining page capture, permitted extraction (Vision escalation remains declined), independent owner/property/current-sale verification and durable verification results; then PropStream eligible batches under the existing $50 cap. The trustee search for1000Canal did not establish current-sale status; leave its hold intact. No messages to trustee or sellers sent.

## Latest verified checkpoint — October 13, 2026

**Work is active and unfinished.** Rehearsal Daily Lists was verified in the signed-in browser after deployment: Daily lead pipeline title; zero input/textarea controls;653 unresolved new notices; $50 cap remaining/$0 committed; two associated properties (one synthetic fixture) held for current-sale verification. Screenshot: this chat's `outputs/wholesaleos-daily-pipeline.jpg`. Removing forms is completed; unattended sourcing/verification/provider processing is not completed.

Collin now has164 detail/first-page captures with zero errors and **40 complete documents /104 page images** in private `work/county-sources/collin-bulk-details/`. Total inventory expects420 pages. Resume full-page capture at inventory offset39; notice4158245 was additionally captured out of sequence. Prefer scanning receipts and letting `captureNotice` resume by hash rather than trusting offsets. Existing CUA helper was loaded from `work/collin_notice_pages_v3.mjs`; repo source is authoritative and adds expected-page bounds. Summary and page evidence remain private, not committed. Inventory dates:26 October6(past),75 November3,56 December1,6 January5,1 April6; dates alone do not establish current status.

Added a local macOS Vision OCR prototype `pipeline/collectors/notice_ocr.swift`, successfully compiled. Sandbox execution failed; the request to run outside the sandbox was **rejected by the user**. Do not repeat that escalation or treat OCR as validated. No OCR results were produced. Continue permitted collection and evidence work; local text extraction still needs an accepted runtime. No paid model workers enabled.

Browser connection recovered with Chrome ID3 (earlier ID1 now denotes MCP Apps). Use fresh tool inventory when resuming. Fresh county tab1348648456 is at the last captured notice; preview deliverable tab1348648465. Older claimed tabs may report debugger unattached; a fresh same-browser tab worked. Avoid the Download PDF event approach, which timed out; visible Next Page traversal succeeded. No collector process remains running between batches.

Next work: remaining124 complete Collin documents, Dallas full-notice collection, accepted bulk extraction and independent identity/current-status checks, durable evidence integration inside WholesaleOS, then exact eligible PropStream batch/quote/result reconciliation and CRM outreach/follow-up flags. Signed-in PropStream UI only, $50 prepaid total, no refills. No real trace purchase, outreach or production promotion occurred.

## Bulk county capture update — October 13, 2026

Collin detail recapture is complete: **164/164 saved, zero errors** after retrying six transient network failures. Optional property metadata is no longer mistaken for a missing notice. Every saved item remains unverified and ineligible for tracing until full evidence review. Three parser tests pass.

Added `pipeline/collectors/collin_notice_pages.mjs`, invoked with the approved CUA browser tab. It traverses the visible county viewer, verifies page counters, JPEG hashes, first-page identity and final pagination, resumes verified local captures, and handles one observed inert click during viewer initialization. Three tests cover counters, capture/resume, loading recovery and tamper rejection. First 15 inventory notices plus notice4158245 have complete local page captures. Full inventory capture and OCR/identity/current-status review remain ongoing. No new records or verified status were written to CRM by these collectors.

UI commit764b288 passed GitHub push/PR CI; Vercel rehearsal deployment dpl_EReBzyuu3xpYrdYjjSeVxaazYF9f is READY at that SHA. Browser acceptance remains outstanding. Production untouched; no trace spend or outreach. Next: complete full-page batches, extract/corroborate evidence, save durable in-app verification results, then eligible PropStream batches with exact budget/receipt reconciliation.

## Resumed — Daily pipeline interface, October 13, 2026

Replaced the Daily Lists operator worksheet with a read-only daily pipeline view: collection receipts, high-priority foreclosure notices, tracing holds, the cumulative budget and saved follow-up status. Removed routine evidence/CSV/quote/contact entry and configuration/scan actions from this page. Queries refresh every minute and are scoped to the signed-in account. The page explicitly states that scheduling/provider automation are not active; this UI change does not establish an unattended pipeline. Verification APIs and internal controls remain intact. Build passed, three UI/identity tests passed, lint baseline checked. Preview deployment/browser acceptance remains to be checked after push.

Collector investigation found real notice pages that have the scan but no optional property metadata; this caused the previous failures. A tested parser correction and resumable recapture are in progress. Next: finish captures, full-page extraction and in-app evidence delivery, then bulk provider and outreach-preparation acceptance. No paid trace or outreach sent.

## Paused at owner request — October 13, 2026

**Controlling product requirement:** bulk county sourcing → AI-assisted verification and deduplication → PropStream skip trace of only new eligible leads → outreach preparation and CRM follow-up, inside WholesaleOS, with no routine manual entry. The owner explicitly rejected the current Daily Lists worksheet (CSV imports, evidence URLs, hashes, quote/contact entry). Do not continue expanding manual forms. Replace the daily page with factual pipeline progress, high-priority leads and exceptions; implement the underlying automation before claiming it is operational.

Saved implementation: `pipeline/collectors/collin_notice_details.py` is a resumable public Collin detail collector. The live run finished before the pause: **164 attempted, 103 metadata/first-page captures, 61 parse failures, zero trace-eligible certifications**. The first reported failures lacked the expected Property Information section; root cause is not yet investigated. Metadata and first-page capture do not establish full notice review, owner identity or current sale status. Script syntax was checked; dedicated tests, full-page acquisition and durable in-app evidence delivery remain unfinished. Collector is not scheduled or integrated into production.

Private resumable evidence (never commit personal data): `/Users/juliodominguez/Documents/Codex/2026-10-13/resume-wholesaleos-from-docs-start-here/work/county-sources/collin-bulk-details/summary.json`, with per-document receipts, HTML and first-page JPEG. Input: sibling `collin-index-review-manifests/inventory.json`. Collector checks saved file hashes on resume. Investigate the 61 failed responses before retries; do not assume these are zero records or verified identities.

DailyLists.tsx and ForeclosureActions.tsx were inspected, but **no UI replacement has been implemented yet**. Existing manual UI remains. Prior pushed commit `9186851` provides bulk result matching; it does not fulfill unattended automation. No provider order, paid trace, seller message or production promotion occurred. The $50 total prepaid ceiling remains. Daily collection automation remains paused.

Resume next:
1. Pull this branch and inspect this checkpoint. Replace the Daily Lists worksheet with account-scoped read-only progress, priority leads and exceptions based on actual receipts; do not display simulated automation status.
2. Investigate Collin parse failures, test the collector, acquire all notice pages and implement evidence extraction/independent identity/current-status verification in bulk. Continue Dallas detail collection too.
3. Deliver evidence and verified candidates into WholesaleOS without duplicate notices or invented certification. Implement AI-assisted provider quote/result handling against the existing idempotent batch/budget APIs; signed-in PropStream UI only, no credential extraction or invented API.
4. Verify real bulk provider results, CRM follow-ups and channel eligibility, then remaining launch gates. Production and unattended schedules remain gated. Continue updating these files and pushing each logical update.

No collection process remains running. Work is paused, not complete.


Owner requirement confirmed October 13, 2026: manage the complete workflow inside WholesaleOS. New Dallas and Collin foreclosure notices are daily high-priority review items. After property/owner verification, trace only eligible new opportunities through PropStream, save matched contacts to the CRM, evaluate channel readiness and track every next action.

## Required app stages

| Stage | Entry evidence | Next action |
| --- | --- | --- |
| High priority — new notice | First receipt of a distinct county/notice identity, Central date | Review all notice pages, property identity, filing and current sale status |
| Ready for skip trace | Verified property and owner, actionable foreclosure status, no reusable contact and no prior completed or uncertain trace for the same opportunity | Build the PropStream batch and verify its exact quote |
| Tracing in progress | Reserved budget and saved request identity; provider submission recorded | Reconcile the original PropStream order; never blindly retry |
| Contact found | Provider result matched to the exact CRM lead/property; contact details, provider receipt, timestamp and actual charge saved | Check contact accuracy, channel eligibility and suppression status |
| Ready for outreach | At least one specific channel passes the application's current eligibility checks | Queue that channel; recheck eligibility at dispatch |
| Follow-up due | Attempt/response recorded with owner and next-action date | Highlight due and overdue actions in WholesaleOS |
| Needs review / suppressed | Uncertain identity, missing result, wrong number, no eligible channel, opt-out or other block | Show the reason and responsible next action; no automatic send |

These are required workflow states, not a claim that every stage is implemented or active. A skip-trace result supplies contact data; it does not create documented SMS consent. Eligibility must be per channel and recipient, not a generic contact-ready checkbox. Opt-outs and wrong-party results must remove the affected destination from pending outreach. Other channels require their own approved operational rules; no alternate-channel authorization is inferred here.

## PropStream handoff

- Use the signed-in PropStream UI as previously directed. Do not invent an API integration or extract browser credentials.
- Batch only verified eligible opportunities. The currently displayed 654 foreclosure notices are evidence-review items, not a ready-to-purchase trace batch.
- Match every provider row to the saved CRM lead/property and trace request; preserve owner/property input and its hash.
- Reuse usable existing contacts. Never trace a repeated county observation as a new lead. Hold submitted or uncertain orders until provider reconciliation.
- Existing authorization remains $50 prepaid TOTAL across all days and orders. Verify the live balance and exact quote; no replenishment, card fallback or recurring purchase. The cap does not authorize tracing every imported notice.
- Save returned contacts, no-match outcomes, provider order receipt and confirmed spend. An empty result must not silently restart paid tracing.
- All queue status, budget holds, returned contacts, readiness reasons and follow-up ownership must be visible inside WholesaleOS. PropStream is the external enrichment step.

## Implementation and acceptance checkpoint

- [x] Daily high-priority notice inbox and dashboard link deployed to rehearsal; 490 Dallas +164 Collin unique notices.
- [x] Durable notice first-seen identity prevents repeat imports from appearing new.
- [x] Existing tracing services support immutable input, reservation/claim/settlement, contacts and uncertain-outcome holds, with cumulative budget enforcement.
- [ ] Verify real foreclosure property/owner/current-status evidence and create the eligible CRM associations. One real Collin property/owner association is verified; its signal remains inactive pending current trustee cancellation/postponement verification. Remaining unresolved unique notices: 490 Dallas + 163 Collin. The synthetic fixture is excluded.
- [x] Implement per-lead verified-candidate quote/reservation/start/result controls, linked follow-up tasks and uncertain-action recovery. Rehearsal migration applied and read-only handoff/budget UI verified; real purchase/result acceptance remains pending.
- [ ] Complete live multi-lead provider acceptance. Bulk CSV review/reservation/start/result controls and atomic server processing are implemented; native PropStream column mapping and real batch receipt/cost acceptance remain.
- [ ] Demonstrate one authorized eligible PropStream order and exact result/charge reconciliation without retracing on refresh or lost acknowledgement.
- [ ] Surface Contact Found and per-channel Ready for Outreach states with recorded eligibility reasons.
- [ ] Complete controlled delivery, STOP/suppression, response and follow-up acceptance before enabling real outreach.
- [ ] Activate daily collection only after collection/monitoring readiness gates; production release remains separately gated.

No PropStream order, spend, seller message, schedule activation or production promotion was performed while recording this requirement. Resume with the real identity-verification gate, then candidate selection and provider reconciliation. Do not mark the pipeline complete from the existence of this plan.

Primary workflow is bulk processing (owner clarification October13): automated notice extraction and verification queues, eligible batch selection, one provider upload/order, matched bulk result import, and assigned follow-ups. Individual lead forms are exception handling, not the daily operating model.

Bulk result matching now has an in-app two-file column mapper and exact owner/property matching with exception exports. Real provider-file acceptance remains open; the implementation does not imply a real trace was completed.
