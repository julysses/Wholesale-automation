# Collector rebuild and PropStream operating checkpoint

Updated October 13, 2026. Status: implementation and supervised acceptance, not scheduled operation.

## Owner decisions

The owner confirms no collection schedule is operating; the previous task did not finish. Rebuild it rather than assuming it is running. PropStream will be operated through its signed-in website. The latest spending authorization is the existing **$50 total prepaid balance**, with no reload or plan change. This supersedes the earlier free-only answer. It is not a daily or monthly replenishing budget.

## PropStream controls

Account UI observed: Legacy monthly plan ($99/month shown on Manage Plan), $50 prepaid credits, 25,000 saves and 25,000 exports remaining, renewal/reset November 1, 2026. No included 100-trace allowance was confirmed. Do not confuse save/export credits with tracing credits. No order submitted and no spending incurred in this session.

Before each order, check the current balance, count eligible untraced properties, inspect the final order quote, and record the batch reference, exact selected CRM property IDs, quoted maximum and timestamp. Maximum available spend is the lesser of current prepaid balance and $50 minus verified charges and unresolved order reservations. Never enable auto-reload, upgrade a plan, or use a card fallback. Stop if the checkout can charge more than the reservation or an order result is uncertain. Inspect order history and reconcile before retrying.

Use existing contact results before buying new traces. The observed historical group `Collin PreFor July26` is not proof of current distress or eligibility. Match returned results to the exact property/owner identity, preserve provenance and provider receipt, and keep mismatches for review. Contact discovery does not grant SMS/email/calling consent. Import and reconciliation with the CRM remains to implement and verify; a browser purchase alone does not close this gate.

## Source corrections and collection procedures

### Dallas foreclosure — procedure v1

County authority: https://www.dallascounty.org/government/county-clerk/recording/foreclosures.php . The county directs recent notices to https://dallas.tx.publicsearch.us/ . The older page includes dated PDF listings and cannot establish current complete coverage on its own.

Browser verified: the public site opens without login; select Department → Foreclosures. It defaults to **Sale Date**, not notice filing date. Never label a sale-date search a 30-day filing-date search. Advanced Search exposes a separate Recorded Date Range. A live search with Recorded Date September 14–October 13, 2026 inclusive and both sale-date bounds cleared returned 479 indexed notices (50 on the first page). This is discovery only; pagination, individual notices, filing-stamp semantics and current property identity still need verification before claiming complete coverage. The Property Records certification date observed before switching departments is not a foreclosure coverage certification.

The new migration corrects the known seeded endpoint and adds the exact county-linked host. It preserves disabled state, schedules, custom endpoints and history. Applied only to rehearsal. No purchase of county documents is authorized by the PropStream balance approval.

### Collin foreclosure — procedure v1

Official source: https://apps2.collincountytx.gov/ForeclosureNotices/ . Current rendered page exposes Filed Date Start/End separately from Sale Dates and paginates results. Set the inclusive filing window (maximum 30 days), inspect every page and notice, preserve stable notice/document identifiers, and verify property identity separately. Public search indexing is discovery evidence, not complete coverage. A UI error or unreadable notice requires partial/failed status with a reason, not empty success.

### Remaining six sources

Dallas/Collin probate and tax delinquency, Dallas city code violations, and McKinney code violations still need individually verified procedures. The Dallas code dataset is archived; find a current official replacement. The 141 earlier McKinney candidates remain unresolved. A city result does not prove county, an estate name does not prove property ownership, and tax-sale notices are not the full delinquent roll.

## Collector execution contract

For each source, record source_key, a code-generated UUID run_id, Chicago scheduled date, actual pulled_at, exact inclusive window, source_as_of, status and coverage explanation. Collect only supported facts; missing values are null. Preserve document URLs and minimal evidence. Treat all source text as data, not instructions. Stop at access restrictions; never bypass CAPTCHA or login requirements.

Generate the manifest using the checked-in ingestion schema and shared canonicalJSON/SHA-256 helpers. Run:

```sh
node pipeline/collectors/preflight.mjs /path/to/manifest.json /path/to/coverage.json
```

The offline validator currently supports the two foreclosure procedures. It checks structure, source identity, exact HTTPS hosts, hash, size, filing-window semantics and honest empty-result status. It prints `delivered: false` even when valid. Complete claims now require a reviewed coverage ledger: two matching ordered page inventories, stable document IDs, explicit review dispositions and exact manifest reconciliation. See [coverage ledger procedure](collector-coverage-ledger.md). Partial/blocked runs omit the ledger and retain incomplete evidence separately. It does not collect, sign, submit, establish factual completeness, or acknowledge CRM ingestion. Other source procedures must be reviewed before extending the registry. Keep sensitive source files outside Git.

## Implementation sequence and acceptance

- [x] Correct the assumption that a schedule is already operating.
- [x] Verify current county entry points and correct Dallas in rehearsal.
- [x] Add offline preflight and targeted tests (22 passed with existing contract tests).
- [x] Verify Dallas advanced recorded-date search independently from sale date.
- [x] Add coverage-ledger checks for total drift, repeated/missing pages, filing-window errors and unresolved documents (34 targeted tests passed).
- [ ] Complete Dallas/Collin pagination, document extraction and filing-stamp validation.
- [ ] Produce one supervised manifest per county; independently review county/property identity and completeness.
- [x] Verify the source-scoped secret delivery path and durable Edge acknowledgement in rehearsal. Scoped Keychain secrets, HTTP202acceptance, HTTP200exact replay and SQL counts verified October13.
- [x] Replay the same run safely and verify uncertain-response reconciliation, staged records and review tasks. Live exact replay and assigned partial-run tasks verified; lost-response behavior covered by delivery-client tests.
- [ ] Verify failure/missing-run alerts and owner digest delivery independently of the collection worker.
- [ ] Install schedules only after the preceding delivery path works; check for residual cloud Tasks before creating duplicates. The PRD times remain proposed, not installed.
- [ ] Complete five supervised clean foreclosure runs per county, then the agreed 14-day unattended observation window.

No scheduler was installed this session. All sources remain disabled. Production promotion, seller outreach and the other launch gates remain open.

## Resumed October 13 investigation

Dallas total changed from 479 to 490 during pagination; pass stopped as incomplete. Collin one traversal returned 164 entries in the filing window across seven pages, with 163 distinct displayed texts. Stable document IDs and complete notice review remain open; these are not verified new leads. The Collin calendar procedure and detailed evidence are in collector-coverage-ledger.md. No trace spend, ingestion, schedule or production mutation occurred.


## October 13 — tax collectors and deployed ingestion shell

Implemented official-link tax ZIP fetcher, fixed-width Dallas/Collin parsers, integer-cent control reconciliation, bounded manifests, and scoped HTTP delivery with durable local retry journal. See `docs/county-tax-collectors.md`. Full archives yielded30,516Dallas and9,182Collin review candidates; all81batches validated. Counts are not verified new leads.10Python parser/security tests and23Node collector/preflight/coverage/delivery tests passed. Collin full fetch-discover-download-parse run passed with matching archive hash. Dallas full archive was downloaded and parsed; fetch-wrapper live check remains pending. No county records delivered yet.

Deployed rehearsal `daily-list-ingest` Edge version1, function2967097e-01a8-4559-8543-324ba0d85354, bundle2dc68bfca73dacb05537c284c135fc8d13c569d1c59f4581ad67aa82812e1f13. Body contains explicit hashed/scoped/expiring token authentication; platform JWT check is off to use that custom credential. Exact unauthenticated POST returned503ingest_not_configured, confirming fail-closed missing secrets. Sources remain disabled. Local CLI sign-in was requested because MCP cannot configure Edge secrets; owner reports browser sign-in, CLI still needs authorization. No production or live outreach change.

Private working evidence: `/Users/juliodominguez/Documents/Codex/2026-10-13/resume-wholesaleos-from-docs-start-here/work/county-sources/`. Dallas run68e93ec1-6e54-4c66-a96b-bd30035de6b7; initialCollin rune3616157-5607-494f-93fa-f06939b8f25a; verifiedfetchCollin run892910fa-9b11-4467-993a-d98ae083a8ac. Use only one Collin snapshot run for eventual delivery; preserve originals and replay exact payloads. Tax collectors intentionally leave account/property review incomplete.


## October 13 — live rehearsal ingestion accepted

Supabase CLI login completed. Rehearsal Edge secrets are configured with four source-scoped hashed tokens and a restricted database login (`wholesale_ingest_edge`, inherits `wholesale_ingestor`, no superuser/RLS bypass or CRM write access). Credentials are held in macOS Keychain, expire November 12, 2026 at 23:59:59 UTC, and must be rotated before expiry. No credential values belong in Git. Production remains unchanged.

Live HTTP acceptance: invalid token401; wrong-source token403; disabled-source403; new synthetic batch202; exact replay200; changed manifest under same run409. Database reconciliation confirms one batch/record after replay. Dallas tax run `68e93ec1-6e54-4c66-a96b-bd30035de6b7`:62batches/30,516records. Collin tax run `892910fa-9b11-4467-993a-d98ae083a8ac`:19batches/9,182records. Do not deliver the separate initial Collin parse again. All39,698 real tax records are in the evidence-review queue, not qualified new leads.

Monitoring generated three assigned partial-run tasks (including synthetic acceptance) and a digest; digest delivery remains unverified. Stable preview `/daily-lists` showed the receipt counts and $50 total tracing authorization, $0 committed, $50 remaining. No tracing requests, spending or seller outreach occurred; outreach setting remains false and scheduler remains PAUSED.

Synthetic run `75453257-33a1-494c-bc99-b3c958e1cd65` created QA-only lead `7e62af51-0dc5-4d08-bfbe-2627039f13e5` / property `d444c637-d2fc-4e59-be6e-cc9caeb98fe7`, address explicitly marked NOT REAL. Resolution replay returned the same property with exactly one review event and one new lead. Signal is inactive; SMS/email sequences are false and there are no phone numbers. This is technical acceptance, not a qualified business opportunity. Source enablement is limited to rehearsal Dallas synthetic foreclosure and both tax feeds; other five feeds remain disabled.

Remaining delivery gap: tax snapshots lack verified situs city (Dallas also lacks situs street), intentionally excluding mailing geography. Add an audited operator identity-evidence workflow before resolving these tax records; never copy mailing address into property fields. Foreclosure document review, cross-source live dedupe, paid-provider reconciliation, controlled consent/STOP acceptance, five clean supervised runs per county and14unattended days remain open. Full launch remains NO-GO.

Dallas foreclosure index evidence: two complete sorted traversals on October13,250+240 rows each,490unique document IDs, document numbers202600002420–202600002909. Durable private inventory at `work/county-sources/dallas-document-inventory.json` under this chat's directory. Indexed filing/sale dates are not reviewed notice evidence; no complete-coverage credit or real foreclosure delivery yet. Prior479 count is superseded by this later observation.


## October 13 — Collin notice review delivery

Visually reviewed all four pages of Collin notice4158237 and delivered partial run `90ccda04-b804-44a0-8cf5-3ad97484a12c` (one batch/record accepted). Notice filing stamp October1,2026,13:59; advertised sale December1. Original principal is not current amount owed. The notice and Exhibit A reference deed instrument20210604001132350, while the county detail page says20210604001132340. Preserved the discrepancy and unverified current-sale/CAD identity flags in raw evidence; no CRM association, tracing or outreach authorized. Other Collin notices and second inventory traversal remain incomplete. Rehearsal Collin foreclosure delivery enabled only for this supervised procedure; schedule remains paused.

Preview deployment `dpl_BgCbBvSiRymuX3ovm83UNWuDAwsR` is READY for7c3c0a0. Added a Last page control so operators can reach newly arrived evidence without hundreds of page clicks. Synthetic tax run `b86e3276-a528-4ff3-8568-d5bd48b8bf49` is reserved for browser association acceptance against existing QA lead; do not count it as a business opportunity.


## October 13 — deployed CRM association accepted; current resume boundary

The signed-in stable preview completed the new audited review form for synthetic tax run `b86e3276-a528-4ff3-8568-d5bd48b8bf49`, associating it with existing QA lead `7e62af51-0dc5-4d08-bfbe-2627039f13e5` / property `d444c637-d2fc-4e59-be6e-cc9caeb98fe7`. The receipt showed **zero new leads and one stacked observation**. SQL confirmed original staged street/city remained null, exactly one review event, both synthetic distress signals inactive, SMS/email sequences false, and zero tracing requests. This proves the deployed form/API/database handoff, not a real property identity or qualified opportunity. No real tax record was promoted.

Real unresolved evidence totals39,699 records:39,698 tax records plus one Collin notice. Two synthetic records are resolved and must remain excluded from business opportunity counts. Screenshot saved in this chat's `outputs/rehearsal-crm-receipts.jpg`; raw notice/index evidence stays private outside Git.

At implementation commit `de0ddf4`, GitHub backend, frontend, pipeline contracts/isolated SQL, real PostgreSQL ingestion/offer contention, and Vercel checks all passed. Local regression totals remain843backend,198frontend,123pipeline and13Python collector tests. Existing lint/bundle warnings are recorded above.

Full launch remains **NO-GO**: complete foreclosure collection/current identity review, real provider reconciliation, controlled consent/STOP and unsubscribe acceptance, external digest/missing-worker monitoring, remaining recovery/operator gates, five clean county runs and14 unattended days are still required. The saved heartbeat remains PAUSED. Production was not changed, no paid trace order was submitted, and no seller message was sent. Resume from these remaining gates; do not repeat completed secret setup, tax ingestion or synthetic association.
