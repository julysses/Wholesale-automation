## Current checkpoint: after-hours form SMS and restricted intake access (2026-10-16)

This section supersedes historical checkpoints below. App deployment is currently fbfa71046af54757553a0ad5ac11e617e0e961fe (READY dpl_6oYGkHv9rCTEVhHrU6VVd7fmkjAN). Handoff fix cd75522 is pushed; CI 38965925591 passed all four jobs.

New after-hours form inquiries now calculate their first eligible contact window in America/Chicago, including daylight-saving transitions. Daytime inquiries retain the one-minute delay and original expiry; deferred inquiries expire fifteen minutes after their next opening. Existing queue rows retain their identity, timing and status; no retries or renewals are performed. The matching next-window handoff migration is already applied to production, and only recognizes a schedule backed by a durable queue row. Application code release is pending at this checkpoint.

Validation: 794 backend tests, 130 pipeline tests, and production rollback SQL acceptance pass. The frontend was unchanged (162 tests previously passed). Restricted wholesale_ingest_edge role was created NOLOGIN, with only wholesale_ingestor membership and a four-connection limit. Live checks confirm no administrator powers, worker membership, CRM SELECT or contacts SELECT. No password or source token has been created yet.

First Mac Keychain approval succeeded: the official Supabase CLI listed production. A subsequent link command is still awaiting a second macOS Keychain approval. User must operate SecurityAgent; computer-use explicitly denies access. Pending execution session 56693 uses CLI v2.79.0, work/intake-credentials, production dvzhzlipbwzzcliujzyz. Do not launch another login, bypass the prompt, use admin DB access as Edge credentials, or reuse rehearsal credentials. Edge INGEST_DATABASE_URL and INGEST_TOKEN_CONFIG remain missing.

Historical Collin promotion remains verified: 78 properties, 74 new plus four reused leads, 77 completed traces, 481 contacts and 78 assigned follow-ups. All collection sources, SMS scheduler and outreach remain disabled, with trace cap zero. Retell ticket 65825 refreshed: Open, acknowledgement only. Twilio 29953072 remains pending internal escalation from the last verified response. No provider messages or trace orders were sent.

Eight monitor findings remain: two SMS, two form SMS, three intake alerts and one legacy intake. The legacy July entry identifies Verifier Bot at 999 Verifier Ln and already has a review task; preserve it as likely synthetic, not a recovered customer. The expired unprocessed October 16 form has a questionable property address but no confirmed test disposition; do not resend it. Provider-accepted and carrier-undelivered messages remain unresolved.

Next: push and deploy the tested after-hours fix; complete restricted Edge/source credentials once Keychain unlocks; prove real production ingestion through ownership and follow-up; resolve carrier routing/callbacks and verify delivery/reply/STOP before activating automation. Full Dallas/Collin source coverage, 85 unresolved Collin notices and remaining PropStream reconciliation are still open. Keep the cumulative $50 cap and existing provider choices. No fully operational launch is claimed.

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
