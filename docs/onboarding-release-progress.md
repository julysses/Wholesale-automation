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
