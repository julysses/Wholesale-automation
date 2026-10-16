## Dallas historical onboarding completed — 2026-10-16, 21:44 UTC

Production promotion 864bcbf3-e3dd-4fca-be7f-0b05ec97035f is complete. Preserved the real Dallas foreclosure run db1c2221-ed79-4ece-bf12-386a84d59477 from rehearsal: one original payload, 490 unaltered source records, 490 first-seen receipts, one complete five-page capture, five extraction receipts and one appraisal matching receipt. Source IDs were mapped by source_key only. No synthetic one-record rehearsal scenarios, active jobs, credentials or tax snapshots were copied. Original capture dates, payload/record hashes and review holds remain intact. This is a historical review-inventory transfer, not a live collection or complete county coverage claim.

Individually reviewed all five saved pages of Dallas notice 330724568 (instrument 202600002461) and its live official DCAD account 38000500510030200. Exhibit A and DCAD agree on the situs and legal description. Current DCAD identity labels are 2027; certified values are 2026 and were not used for qualification. Created property 5abd6cd5-e4f5-421f-b58a-3a470ded6bd8 and lead e4052c46-917a-4a15-9875-616f880f2496, assigned to approved owner 89f3b3f6-5a88-4b79-b3f4-461e0cd626a2. Pending property follow-up: 91dd619b-ed42-af60-91d5-7691bd64589e. Inventory review task: e629dea8-9a37-81f1-6828-1be1cf695025. The October 6 sale outcome is unverified: signal remains inactive; no tracing or outreach permitted.

Production now has 82 associated properties, 654 source records, 84 review events, 17,448 leads and 136 tasks. Pending property reviews are 570: Dallas 489 plus Collin 81. Completed trace requests remain 77, SMS fingerprint remains 5b888c800d9ce2ec73d6bba19a8d1e49, every source gate remains disabled and the SMS scheduler remains false. Exact production rollback passed before saving; no fixtures survived. Committed replay returned the original receipt and direct assertions verified no duplicate rows/tasks. Authenticated Daily Lists visibly shows Dallas capture/matching receipts, 82 properties and the reviewed Dallas property's current-sale hold. Proof: current chat outputs/WholesaleOS-Dallas-Onboarding.png.

Executed operation: pipeline/operations/promote_dallas_20261016.sql. Private reconstruction, source evidence, reviewed note, staging, rollback and commit packets are in work/dallas-historical-promotion/. source-evidence.json contains only the scoped historical run metadata and capture/extraction/appraisal receipts; local original payload SHA256 was checked against the live rehearsal receipt. All seven table-array checksums passed against authoritative rehearsal checksums inside the production rollback and commit. Source record/raw checksums were refreshed immediately before commit. No runtime code or schema changed, so no app redeploy is needed.

Tax inventory reconciliation: Dallas real snapshot 68e93ec1-6e54-4c66-a96b-bd30035de6b7 has 30,516 unresolved accounts in 62 batches. Collin original 892910fa-9b11-4467-993a-d98ae083a8ac and later 311ee85d-e46c-4c49-bdf6-c46bd3272a19 each contain 9,182 unresolved accounts in 19 batches. Full source-ID join proved 9,182 identical record JSON values, zero changed/new/missing accounts. Preserve one canonical original snapshot for migration, retain the duplicate receipt as history, and do not double the operational review queue. The synthetic/resolved one-record Dallas tax and foreclosure runs are excluded. The 39,698 real tax candidates remain in rehearsal pending scoped historical migration and property/current-tax review.

Next: reconcile the tax snapshots and remaining county evidence; retain the pending one-record HTTP intake exception request and do not open a source gate without that answer. The credential approval is already fulfilled. SMS provider delivery/reply/STOP remains a separate launch gate. No new support messages, spend or outbound contact occurred. Goal remains active; this turn made verified production onboarding progress.

## Intake verification checkpoint — 2026-10-16, 16:36 Central

Approved production intake credentials remain installed. Live ACL checks confirm wholesale_ingest_edge has inherited SELECT/INSERT on the intake tables and first-seen notice receipt, no lead/contact reads, no administrator privileges, and a four-connection limit. All eight source gates and the SMS scheduler remain disabled; the GPT collection automation remains PAUSED.

Production database rollback acceptance passed for saved Collin notice 4158381: insert run/payload/record/jobs, resolve to existing lead 90fe23ec-ddc0-4278-8964-dd9726fd931d, replay the review, preserve the existing assigned pending task, and assert no duplicate leads/properties/tasks or trace/SMS changes. No fixture survived rollback. Counts remain 17,447 leads, 134 tasks, 81 associated properties and 77 trace requests; SMS-event fingerprint remains 5b888c800d9ce2ec73d6bba19a8d1e49.

Validation boundary: the management connection cannot SET ROLE wholesale_ingest_edge (membership does not include SET). The initial impersonation test failed before insertion; no grants were broadened. The passing production rollback used the management connection and therefore is not restricted-login HTTP acceptance. Updated pipeline/integration/ingress-postgres.ts to load the actual restricted-login migration and foreclosure first-seen trigger, then connect with that login against disposable local PostgreSQL/TLS. The complete integration run passed actual handler acceptance, concurrent duplicate serialization, lost-ACK replay, changed-payload conflict, expiry, disabled-source rejection, one notice-history receipt, restricted role attributes and denied lead/contact reads, source updates and record deletes. Existing concurrent trace-cap and scoring tests also passed. No runtime or production schema change was needed.

Prepared production HTTP test is NOT SENT: work/intake-acceptance-20261016/batch-0000.json, run 4778792b-4655-4b01-bdbb-e1489d7e9a7c, one historical notice 4158381, records hash f53965b2c837f020ef3a82eee43adef07796b577826718c4ab485c87c0e49be8. It is partial historical evidence, not fresh collection or complete coverage. Expected: HTTP 202 then identical replay 200; one batch/record; reuse the existing lead and follow-up; zero new leads, trace orders or messages. Source activation remains pending the separate user request to briefly open only Collin foreclosure intake for this test and restore it immediately. Credential approval does not authorize changing the collection pause. Preserve run ID and payload on uncertain outcomes; use finally cleanup to restore the gate. Do not invoke SMS or tracing workers.

Private evidence: database-path-rollback.sql, restricted-path-rollback.sql (failed impersonation harness), expected-review.json, prepared.json and verification-results.json in that ignored directory. Continue full Dallas/Collin coverage and property review while awaiting provider resolution and intake-test approval. Keep Twilio, Retell, PropStream and the cumulative $50 cap. Full operational launch remains unverified.

## Latest verified onboarding progress — 2026-10-16

Four existing Collin notices were resolved through public.resolve_reviewed_list_record after individual property evidence review. Production now contains 81 associated properties (previously 78); unresolved records are 81 (previously 85). Three new leads were created and one existing lead was reused. Each of the four has an approved assigned owner and one pending follow-up task. All four newly reviewed signals remain inactive because current sale/cancellation status has not been verified. No tracing or outreach was authorized.

Evidence: refreshed Collin public appraisal dataset ahis-pci3 returned one row per parcel, each dated 2026-10-16. Original county notice images were visually reviewed for the matching legal descriptions (subdivision, block, lot); county index parcel/address references and appraisal situs/owner corroborate them. Parcel 2070764 was additionally verified in the live Collin CAD detail page. Preserve the distinction between property identity and title/current-sale verification. Full private evidence and exact SQL are in work/onboarding-property-review/, including owners-20261016/snapshot.json, review-packet.json, resolve.sql, resolve-rollback.sql, verify-replay.sql and commit-result.json. Original captures/OCR remain at /Users/juliodominguez/Documents/Codex/2026-10-13/resume-wholesaleos-from-docs-start-here/work/county-sources/.

Committed notice mappings:
- 4158381 -> property 4fed3771-e259-4bbb-a331-dc5403c4aa82, lead 90fe23ec-ddc0-4278-8964-dd9726fd931d (new).
- 4159493 -> property 982e50b9-eb9a-425a-ad1b-8e1586007366, lead 43b81dc4-9988-44d4-96bc-b24520872078 (new).
- 4160151 -> property 6583e8e5-6f85-4791-bcc5-df8e339096b9, lead 8332b034-6803-4b56-8142-171f6325a8c7 (reused).
- 4160506 -> property 02086707-9be1-4483-b445-2f2e61f2ae69, lead 7be03e5d-fd0c-4969-bd9a-054fab69aa5f (new).

Validation: production rollback assertions passed before saving; the committed results were queried directly. Replay of all four reviews returned the existing associations without adding leads, properties, review events or tasks. SMS-event fingerprint remained 5b888c800d9ce2ec73d6bba19a8d1e49; trace requests remain 77. Zero sources enabled; SMS scheduler disabled. Authenticated Daily Lists visibly shows 81 associated properties and 81 earlier notices awaiting review, including the new property hold. Screenshot in current chat outputs/WholesaleOS-Review-Queue.png shows the reduced review backlog.

No code fix or redeploy was required. An initial suspicion about the Collin CAD hostname was disproved: production resolve_reviewed_list_record already accepts esearch.collincad.org via an existing migration. Do not add a duplicate host migration. Full goal remains active; next resolve the remaining source evidence, prepare controlled real intake acceptance without silently enabling collection, reconcile Dallas/tax coverage, and complete provider delivery/reply/STOP validation before launch. Keep Twilio, Retell, PropStream, the $50 cumulative cap and paused sending/collection constraints.

## Current checkpoint: after-hours form SMS and restricted intake access (2026-10-16)

This section supersedes historical checkpoints below. Production app code 4cfc67bede74c29d98246d5ef352f788cb4f29d4 is READY as dpl_7fAd7VtVKVDtc5rkkvTVToMaxoUG; wholesale-automation.vercel.app is assigned with no alias error. CI 38967115652 passed all four jobs. Live /api/health, /setup and /daily-lists return HTTP 200. Channel-table fingerprints match before/after release, and the SMS scheduler remains disabled. Handoff fix cd75522 is also included.

New after-hours form inquiries now calculate their first eligible contact window in America/Chicago, including daylight-saving transitions. Daytime inquiries retain the one-minute delay and original expiry; deferred inquiries expire fifteen minutes after their next opening. Existing queue rows retain their identity, timing and status; no retries or renewals are performed. The matching next-window handoff migration is already applied to production, and only recognizes a schedule backed by a durable queue row. Application code and matching database migrations are now released.

Validation: 794 backend tests, 130 pipeline tests, and production rollback SQL acceptance pass. The frontend was unchanged (162 tests previously passed). Restricted wholesale_ingest_edge LOGIN is now configured with explicit user approval, only wholesale_ingestor membership and a four-connection limit. Live checks confirm no administrator powers, worker membership, CRM SELECT or contacts SELECT. Password and four source tokens expire 2027-01-14T21:12:32Z; rotate before that date. Production Edge secrets INGEST_DATABASE_URL and INGEST_TOKEN_CONFIG are installed. Plain source tokens are stored only in scoped Mac Keychain items wholesaleos.production.collector.<source_key>, account <source_key>. Temporary generated password, token and verifier files were removed after verification. Non-secret provisioning status and acceptance results remain in ignored work/intake-credentials. Security advisors remain at the existing 29 INFO and three WARN findings.

User approved both Mac Keychain prompts and explicitly approved the restricted production login, Edge secrets and four collector tokens. The previous automatic approval rejection is resolved by that specific authorization. Official CLI v2.79.0 is linked in work/intake-credentials to production dvzhzlipbwzzcliujzyz; set SUPABASE_TELEMETRY_DISABLED=1 and DO_NOT_TRACK=1. Nine live HTTP checks passed: unauthenticated requests return 401, all four tokens loaded from Keychain reach the database and return source_disabled_or_unknown, and cross-source requests return source_not_authorized. SQL verifies zero probe runs saved, 78 historical properties retained, zero enabled sources and unchanged SMS channel fingerprints. This proves authentication, source isolation and database connectivity, not a new accepted collection run. Never substitute administrator or rehearsal credentials.

Historical Collin promotion remains verified: 78 properties, 74 new plus four reused leads, 77 completed traces, 481 contacts and 78 assigned follow-ups. All collection sources, SMS scheduler and outreach remain disabled, with trace cap zero. Retell ticket 65825 refreshed: Open, acknowledgement only. Twilio 29953072 remains pending internal escalation from the last verified response. No provider messages or trace orders were sent.

Eight monitor findings remain: two SMS, two form SMS, three intake alerts and one legacy intake. The legacy July entry identifies Verifier Bot at 999 Verifier Ln and already has a review task; preserve it as likely synthetic, not a recovered customer. The expired unprocessed October 16 form has a questionable property address but no confirmed test disposition; do not resend it. Provider-accepted and carrier-undelivered messages remain unresolved.

Next: prepare a controlled real-source acceptance batch and obtain a change to the current paused-source constraint before enabling its intake; prove durable acknowledgement, retry deduplication, normalization, ownership and follow-up; resolve carrier routing/callbacks and verify delivery/reply/STOP before activating automation. Full Dallas/Collin source coverage, 85 unresolved Collin notices and remaining PropStream reconciliation are still open. Keep the cumulative $50 cap and existing provider choices. No fully operational launch is claimed.

## Latest: Retell intake handoff alerts corrected (2026-10-16)

Production UI code fbfa71046af54757553a0ad5ac11e617e0e961fe is deployed READY as dpl_6oYGkHv9rCTEVhHrU6VVd7fmkjAN on wholesale-automation.vercel.app. CI 38962289678 passed all four jobs. Authenticated setup UI verified PropStream and Twilio + Retell with live monitoring; proof is in the current chat outputs/WholesaleOS-SMS-Setup-Live.png.

Applied reconcile_retell_intake_handoffs migration to production. Old notification finalization did not recognize Retell queue acknowledgements or no-SMS-required outcomes. Five historical alerts reconciled; monitoring resolved five incidents (13 to 8), with no new incidents. Scheduled handoff requires a persisted queue row; uncertainty, missing schedules, consent/suppression holds and failed owner email remain review. Completion describes intake handoff, never message delivery. Existing SMS queue and SMS-event fingerprints are exactly unchanged. Scheduler remains false.

Validation: all 130 pipeline tests pass, including future and historical outcome classification, missing queue receipts, claimant restrictions and no replay. Real production rollback QA passed with zero retained fixtures; Retell review jobs remain independently monitored. Security advisors unchanged: 29 INFO and three existing WARN findings. No messages or trace orders sent.

Remaining findings: SMS 2, form SMS 2, intake alerts 3, legacy intake 1. The legacy July 10 submission has no current form configuration or request manifest; investigate its source and contents before assigning a recovery disposition. Do not delete it or treat it as processed without evidence.

Credential blocker: official Supabase CLI v2.79.0 completed browser sign-in, but Keychain retrieval failed. Resumed check launched macOS SecurityAgent; computer-use explicitly refuses that protected app. User has been asked to approve the Keychain prompt themselves. No production ingest login role or source credentials created; Edge still needs INGEST_DATABASE_URL and INGEST_TOKEN_CONFIG. Do not bypass the OS prompt, weaken Keychain access or substitute admin/rehearsal credentials. Sources and GPT collection schedule remain paused pending genuine intake acceptance.

Next: finish restricted production intake credential configuration after Keychain access, prove a real source run and downstream ownership/follow-up, reconcile remaining monitor incidents and resolve provider delivery callbacks with Twilio/Retell. Full Dallas/Collin and website onboarding scope remains open; no operational-launch claim.

## Latest: production intake transport and setup guidance (2026-10-16)

Historical Collin promotion remains complete (78 properties, 77 completed traces, 481 contacts and 78 assigned follow-ups). Production Edge Function `daily-list-ingest` version 1 is ACTIVE (id `86013dad-a079-40f4-8ada-4dc40452dbc6`), but its HTTP response is `ingest_not_configured`: production `INGEST_DATABASE_URL` and `INGEST_TOKEN_CONFIG` are absent. Dashboard confirmed both missing. No production LOGIN ingestion role or collector credentials have been provisioned. Sources, trace spending, outreach and SMS scheduler remain disabled.

Current changes: delivery explicitly selects rehearsal or production, requires the corresponding source-scoped Keychain credential, and stores destination/key identity in project-specific receipt journals. Cross-project and cross-key receipt reuse is rejected before network access. Legacy generic journals are preserved; they are not proof of production acceptance. Added credential-routing tests to CI. Full pipeline suite: 129 passing; Keychain routing: 6 passing.

Setup guidance now uses PropStream and Twilio + Retell, marks other providers optional, removes obsolete manual migration instructions and distinguishes connection checks from actual intake/message delivery. The SMS step exposes existing launch monitoring without enabling sending. Frontend build and all 162 tests passed; lint has no new findings (149 preexisting). Production deployment of this UI update is still pending at this checkpoint.

Supabase CLI read-only `db query` and `projects list` stalled without output; process inspection confirmed they remained running. They were deliberately interrupted instead of interpreting a timeout as failure. MCP SQL/deployment and authenticated Dashboard access work. Use a working supported secret-configuration path; never substitute an administrator DB connection or rehearsal collector credential.

Next: publish/verify the updated setup UI, provision the restricted production ingestion connection and source credentials, validate a real source receipt and downstream normalization/assignment, then update the paused GPT schedule to the production checkout. Preserve the original full scope: Dallas and Collin foreclosure/tax intake, remaining 85 unresolved Collin notices, PropStream reconciliation within the cumulative $50 limit, actual provider delivery/reply/STOP verification. No full operational launch claimed.

## Latest: historical Collin data now live (2026-10-16 20:09 UTC)
See docs/onboarding-promotion-2026-10-16.md for the authoritative current checkpoint. Promotion 2e91ac73-af2d-410b-860c-b7e249212408 is complete: 78 properties, 74 new leads + 4 reused, 77 completed traces, 481 contacts, 78 assigned follow-ups. Exact rollback validation and committed replay passed. Authenticated UI confirmed saved results/contacts/follow-up. Collection, spending and outbound messaging remain disabled. Broader Dallas/tax inventory, 85 unresolved Collin notices, live scheduled ingestion, stale workflow guidance and carrier delivery remain pending. Older empty-production/data-not-transferred notes below are historical.

# Onboarding production integration — October 16, 2026

Goal: keep Twilio and Retell; complete onboarding while carrier support is pending.

## Current change
Selectively ported county intake, evidence review, PropStream reconciliation and monitoring from collector commit 7337de2 into current production branch. Existing website/SMS repair code is preserved. Land/offer changes and Retell branch versions were excluded.

Added accessible property verification with pagination and PropStream handoff controls to Daily Lists. Added atomic county-lead ownership and a per-lead review task. No owner means the property association rolls back; existing assignments and completed tasks survive. No outreach is triggered by these operations.

## Verified before release
- 787 backend tests pass.
- 162 frontend tests pass; production build passes.
- 127 prior pipeline tests plus the selected-migration sequence/assignment test pass.
- 19 Python county-collector tests pass.
- Real localhost PostgreSQL/TLS intake, duplicate and lost-ACK replay, restricted-role access, trace-budget concurrency and scoring-claim concurrency pass.
- Lint has no new findings; 149 preexisting findings remain.
- Production schema and intake roles absent; no existing public function name conflicts with selected migrations. SMS scheduler remains disabled.

## Correction to earlier review
Three unassigned historical website leads are closed synthetic/test records. Two lack tasks; another task is completed. They are not missed active inquiries. Do not reopen them or fabricate recovery notifications.

## Release sequence
- [x] Reconcile branch and selectively integrate source.
- [x] Test combined application and exact migration sequence locally.
- [x] Apply all 32 manifest migrations to production; rollback QA confirms ownership, per-lead task, replay preservation, notifications, suppression and snapshot/access contracts.
- [x] Deploy 8feb89b24df764f457336cf56bf14d9495bc5c0e and inspect authenticated Daily Lists: all snapshot sections load, property reviews and PropStream controls open.
- [ ] Reconcile/transfer existing source and PropStream receipt graph without duplicating leads, requests or spending.
- [ ] Verify a matched batch in production including ownership, task and held contact history.
- [ ] Connect scheduled ingestion to production after acceptance; observe a genuine source run.

Do not activate SMS, order new traces, erase suppression history, copy credentials, or promote the collector branch wholesale. All source collection starts disabled in the production migration. Historical raw data expiry and missing provider delivery evidence remain explicit review items.

Weekly monitoring retains expired raw evidence and contacts for explicit maintenance review; it no longer purges them as a side effect. A transient connector request error was reconciled against migration history and absent columns before applying successfully. No data transferred or sending enabled. Live rehearsal inventory: 79 properties, 77 trace requests, 481 contacts, 8 runs, 105 raw payload batches, 49,537 source records and 81 review events.

## Live checkpoint
Deployment dpl_ERRBVokFmZdqXUubwJn2umGNMQR4 is READY and serves wholesale-automation.vercel.app; aliasError=null. GitHub CI run 38957420971 passed for 8feb89b. Production schema, sources, all 32 selected migrations and ownership task trigger are installed. Production collector data is still empty, sources disabled, trace daily cap zero, outreach false, SMS scheduler false. CRM/Hilltop/Jays availability passed. No new tracing, contact messages or model calls were made by this rollout.

Pre-transfer identity check: 79 rehearsal properties, one address marked synthetic/test; 77 completed requests. Four property-address/city/state matches exist in production and all four already use the same lead IDs, with no ambiguous duplicate keys. All four have completed traces. Do not clone them. One non-test property has no completed trace and needs separate evidence review.

Next work: preserve original IDs and receipt graph across source-key mapping, confirm source operator IDs exist in production, preserve 77 completed-order receipts and all contact holds before enabling collection. Add a durable, replay-safe promotion receipt and run a rollback rehearsal of the exact transfer. Never present a transferred historical source record as newly collected. Keep raw county evidence private and out of Git. Avoid duplicate tasks when importing original follow-up task IDs and the new county-intake task.

Also found stale operator guidance in WorkflowGuide.tsx: it tells users to rerun seven migrations, implies CSV import clears DNC, and promises automatic SMS delivery. Correct those claims in the next UI update using actual behavior; do not copy unavailable Human Offer Review instructions from the older collector branch.

Goal remains active. This turn made production code/schema progress; remaining gates are data promotion, live source intake, assignment acceptance on the promoted batch, and carrier delivery support.

## Promotion preparation update
Applied migration 20261016195408_onboarding_promotion_receipts to production after all 128 pipeline tests passed. It adds private, RLS-protected promotion receipts and preserves existing assigned follow-up tasks (including completed tasks) when an imported property is associated. Live rollback QA confirms historical-task preservation, approved ownership, suppression, notifications and access restrictions. No real lead data promoted yet.

The first complete historical transfer scope is the Collin foreclosure run a0c09287-a888-4e8e-97ea-ab4964e5ab69: 78 properties, 164 source records, 79 review events, 77 completed traces, 481 contacts and 77 original follow-up tasks. Private export is under ignored work/onboarding-promotion/. Source configuration is limited to id/source_key; external receipts require inspected, allowlisted fields. No credentials or active job queues are to be copied. Broader Dallas/tax ingestion remains required before launch.
