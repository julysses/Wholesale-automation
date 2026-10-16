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

# October 16 onboarding continuation

Read `onboarding-release-progress.md` first. Production now includes Daily Lists and the 32-migration intake subsystem at deployed code 8feb89b (deployment dpl_ERRBVokFmZdqXUubwJn2umGNMQR4 READY, CI passed). Authenticated UI verified. Collector data has NOT been transferred; source collection and SMS remain off. Next: preserve and promote the existing receipt graph and completed traces, resolving four existing production lead matches. Goal remains active.

# October 16 recovery checkpoint

Read `launch-review-2026-10-16.md` first. App repairs ae12ad9 and 2dec1ff are deployed; monitoring f5f7934 applied to production. Full automated launch remains blocked by carrier filtering and rehearsal-to-production collector handoff. SMS scheduler stays paused. Twilio ticket 29953072 is Hold with internal escalation confirmed. No spend or SMS sent in this review.

## Provider support submitted — October15,2026

User explicitly approved sending the prepared investigation to Twilio and Retell. Both submissions verified in authenticated portals:
- Twilio ticket29953072, P2 Degraded, New, https://help.twilio.com/tickets/29953072 . Submitted3:44pmCentral. Includes failed messageSID, Retellchat/agent/version, verified serviceSID, prior delivered example, START/fresh form consent timeline, paused state and request for filtering/routing/delivery-callback investigation.
- Retell ticket65825, Open, https://support.retellai.com/?durationMs=31536000000&tab=issues&issueNumber=65825 . User completed email-code login. Portal confirmed request received; references Twilio ticket29953072.
No credentials or recipient phone/address included in submitted text. No paid support upgrade, retries or sends. Scheduler remains paused per previous verified state; no activation changes this turn. Await provider response before concluding cause or resuming. Submission proof screenshots in chat outputs/twilio-support-29953072.png and retell-support-65825.png. Existing authorization covers these support investigations; do not ask again just to continue them.

## DELIVERY BLOCKED — scheduler PAUSED October15,2026

Twilio Console confirms owner test SM0ad8ce793ccef33ea439760c1de917e0 UNDELIVERED error30007, created20:33:32UTC. Retell accepted/generated message, but carrier delivery failed. UCS2,5segments,$0.0415 listed. Message had no Messaging Service SID. Earlier Oct7 delivered message SM86c2dfa57821f764b97254659f925191 used MGaf5837f7a7cad183e8b38b1147728562. Do not assume missing serviceSID caused30007. Sender belongs to verified A2P Low Volume Mixed service; current campaign expressly covers opted-in property inquiry updates and registered sample begins 'Thanks for requesting an offer.' Failed text used longer investor pitch.

Paused private.retell_sms_scheduler.enabled and cron active=false. Application env sending flags stilltrue, so do not manually invoke worker. Owner job changed review; sms_events updated undelivered with carrier30007 and confirmed SID. No retry. Carrier failure and campaign/route review remain blockers; do not claim live delivery works. User confirmed nonreceipt after3:33 send. START reconciliation remains valid, history preserved. Need campaign-aligned first acknowledgement and verify Retell sending route/callback delivery integration, then explicitly controlled test. If provider investigation needed, obtain user authorization before contacting support. See docs/retell-carrier-support-draft.md (NOT SENT).

## Re-subscription reconciled; delivery investigation ongoing — October15, 3:33pm Central

Verified owner START event8275990d-ca46-5f67-8082-cf577036ce00 at20:26:33UTC, followed by fresh Jays consented form a7b6f49b-f460-4619-a22d-8afe776336d8 at20:28:22UTC. Added audited sms_resubscription_reviews with operator-only writes and helper requiring matching Twilio START after STOP and matching fresh form disclosure. Original STOP/DNC history preserved; manual lead DNC and later STOP still block. Applied reviewed_sms_resubscription and preserve_unclassified_dnc migrations. Rollback QA passed unreviewed START blocked, invalid START blocked, valid review allowed, laterSTOP/manualDNC blocked, claim success and access restrictions.69 targeted Python tests passed.

Recorded review for confirmed owner historicalSTOP and recovered latest unattempted form within its original15-minute deadline. Job e2e9231a-27ae-566f-8e3d-30c6096e5013 processed by scheduler20:33:29UTC; worker200 processed1/sendingtrue. Retell accepted chat_3e830c21a691319298d4d773598, publishedV1, generated personalized welcome at15:33:31CT. User explicitly still reports no delivery. NO RETRY: accepted is not delivered. Inspect Twilio message logs (Chrome tab1348648971), Retell chat tab1348648871. Calls and native AI reply forwarding still off. No provider delivery callback in CRM yet. Need carrier outcome and fix delivery failure before another test.

## Live test diagnosis — October 15, 2026, 3:17 p.m. Central

User reported Hilltop submission without SMS. Production has no recent Hilltop receipt (latest October9 Central); one new Jays seller receipt at20:17:31UTC, submission557529d4-8225-4428-88a8-0791935a046f, lead50bc5279-2a96-4176-a6b4-adc364313387. Consent accepted and rendered disclosure matches. Intake notification seller_sms=consent_or_suppression_hold; owner_email=accepted. No Retell job/provider attempt created. Phone ending0280 matches durable Twilio STOP opt-out dated October6 Central (October7 03:30UTC), registrya412d09e-fe46-513b-b2d8-bfc8f252f259. intake_phone_status suppressed=true; current lead dnc=false does not override phone-wide registry.

Asked user to confirm whether3:17p.m./ending0280 is their test because reportedHilltop differs from storedJays source. Do not assume identity or remove DNC. Twilio START can re-subscribe carrier side; current CRM deliberately retains STOP until reviewed, so START alone is not sufficient to promise app delivery. Need confirm test identity, observe new opt-in and reconcile suppression explicitly before any fresh test. No sending configuration changed. Production scheduler remains enabled; empty queue is expected for suppressed inquiry.

## LIVE production SMS — October 15, 2026

Owner explicitly requested live activation without recipient restriction. Production code b94d086 deployed READY as dpl_F1jXupfYoa6HUx6C27SwzYg5e8nY; wholesale-automation.vercel.app alias assigned. Saved production RETELL_FORM_SMS_ENABLED=true, RETELL_SMS_LIVE_ENABLED=true, SMS_LIVE_ENABLED=true, RETELL_SMS_LAUNCH_APPROVED=true and RETELL_SMS_ALL_CONSENTED_FORMS=true. No acceptance-verification claim: real handset evidence pending owner test.

Production Supabase scheduler enabled=true and cron wholesaleos-retell-form-sms active=true, every10seconds. Tick verified idle/requestedfalse with zerojobs. Authenticated production worker request6 returned200 processed0/sending_enabled=true. Read-only request5 returned200 connectedtrue with agent/version/published/callback checks alltrue. Calls, nurture and experimental AI reply forwarding remainOFF (production flags absent/defaultfalse). Replies/STOP go through existing Twilio production CRM handler. No county collection, PropStream spend or cold-lead campaign activated; $50 cap preserved.

Final backend705 passed; targetedSMS/form102 passed; frontend140 passed, production build passed, lint no new findings. Earlier production rollback SQL verified queue timing/claims/sharedledger/expiry/DNC and carrier reply/duplicate/STOP/START/followup. No actual SMS sent during QA. Owner will test Hilltop https://hilltophome.co/get-an-offer and Jays https://thejaysdallas.com/sell with SMS consent. Expect due+60seconds plus up to10seconds scheduler and carrier delay, within9am–7pm Central.15-minute expiry means after-hours forms may expire without automatic SMS. Prior accepted-chat guard and24h shared cooldown block second initial SMS to samephone across forms. Do not clear DNC or ledger to force test. Actual delivery, real reply and STOP acceptance still need observation. Do not ask for an owner-phone allowlist again.

Emergency stop: deactivate cron and private.retell_sms_scheduler.enabled; disable production RETELL_SMS_LIVE_ENABLED and redeploy. Never replay uncertain/review or expired jobs without reconciliation.

## Current launch decision — October 15, 2026

User explicitly said "do not restrict. Make it live and I will test when it is live". Supersedes historical owner-only test instructions below. Added RETELL_SMS_LAUNCH_APPROVED and RETELL_SMS_ALL_CONSENTED_FORMS, retaining consent, DNC, phone match, expiry, contact hours and shared duplicate limits. Production settings saved; deployment and scheduler activation in progress. 102 targeted tests pass. Calls, nurture and experimental AI reply forwarding remain OFF by absent production flags/default false. No handset delivery claimed. See docs/retell-live-qa.md. Do not request owner-phone identification again.

## Additional QA findings

Frontend production build passed; lint regression gate passed (149 existing findings, zero new). Live unsigned Retell and Twilio callbacks both rejected401. Production rollback tests repeated successfully for carrier replies, duplicates, phone-wide STOP, late replies and task preservation. Fixed missing wrong-number classification to match the agent prompt: those replies now suppress and never forward to Retell.62 targeted SMS tests pass. Pinned-release probe deployment ad2a6b1 was queued; superseding with this fix. Live handset test still awaits owner-identified form submission; no messages sent.

## Live-test QA in progress — October15,2026

User requested all QA and live testing. Full backend suite692 passed; frontend140 passed. Strengthened read-only production probe to verify configured agent ID, pinned version, published=true and exact production callback.23 targeted probe/worker tests pass (includes3 new negative cases). No sending enabled.

Added tests/sql/retell_form_sms_production_qa.sql and executed against production in a rolled-back transaction: no early claim, one due claim, no duplicate claim, shared Retell/Twilio limits, expiry, DNC and restricted queue access passed. Initial fixture omitted required city; corrected fixture and reran successfully. No test records persisted.

Owner test identification requested: submit Hilltop form with their own mobile and SMS consent, then identify name/time. No answer yet; do not guess owner from recent leads or use historical allowlist. Pending real carrier delivery/reply/STOP test cannot be replaced by unit tests. Native Retell redirect still unverified/OFF. Retell UI shows chat_started, chat_ended, transcript_updated and chat_analyzed selected on draft inherited from V1.

## Production credential approval fulfilled — October15,2026

Owner explicitly approved production API/signing/scheduler credentials. Saved existing Retell key as Production RETELL_SMS_API_KEY; aligned Production RETELL_WEBHOOK_SECRET; saved new Production CRON_SECRET and matching encrypted production Vault retell_sms_worker_bearer. No secret values/files/logs/git. Do not ask again for this scope.

Credential deployment dpl_3jedu2s9tqHe4UTu1Y4D5svPoi2r READY. Production pg_net checks: request1 invalid bearer401; request2 valid200 connected=true, dispatch_authorized=false; normal worker request3 returned200 processed=0,sending_enabled=false. Retell built-in callback Test visibly reported success. No SMS/calls created; this is connection verification, not delivery evidence.

Published Retell V1 Production website SMS - SENDING OFF with callback https://wholesale-automation.vercel.app/webhooks/retell. V0 rehearsal preserved; editable draft now V2. Config saved Production RETELL_SMS_AGENT_ID=agent_193fc3ebd9844b50d54352f200, VERSION=1, FROM_NUMBER=+14698049920, SENDER_NAME=the automated assistant. Deployment dpl_8GuNAwL4TWNKmGqcS4HABrJavfZC verified READY on production aliases with those config values. All activation flags remain false/unset and scheduler/cron inactive. No phone agents assigned.

Both website repository handlers default to production CRM: Hilltop /api/get-offer -> /api/forms/hilltop-home-co/submit; Jays /api/intake sell -> /api/forms/the-jays-dallas/submit. Deliberately invalid non-contactable live submissions returned upstream422 (Hilltop) and email-validation422 (Jays); no leads/messages created. This verifies upstream validation, not successful intake/delivery. Environment overrides still possible; actual owner receipt must be observed in production.

Next: owner identifies their own form submission while sending OFF, so phone is captured through website as requested. Do not guess owner from latest lead. Verify successful receipt/consent/CRM notification before scoped sending. Build finite owner-only testing for both forms without disabling global cooldowns or DNC. Existing prior accepted chat guard and 24h cooldown block same-phone second test. Provider-native reply redirect compatibility remains unproven; routing flag OFF. Verify actual chat delivery/reply/STOP under bounded owner test, then disable test again. Do not claim one-minute handset delivery is ready or guaranteed.

Screenshots in chat outputs: production-retell-callback-success.png and production-scheduler-vault-saved.png. User approval is complete, not a remaining blocker.

## Latest update

Release 421a373 pushed and production deployment dpl_GyRNtdbmQanGo8J7QDnWmSRoVSzc READY with public aliases. Callback fix f492bad production deployment dpl_6K6BP6u648RjBofA1oyvUEMEqXV2 verified READY with wholesale-automation.vercel.app assigned. Production credentials approval requested in chat; prepared Vercel Secret RETELL_SMS_API_KEY, Production only, value EMPTY. Do not save until answered. Bundle approval covers API key, production webhook signing alignment, scheduler bearer in production Vault; no bypass needed.

Retell documented Get Chat omits phone fields. Updated callback resolver to use exact saved chat ID when telephone fields are absent, rejecting conflicting lead/phone metadata. 143 targeted tests pass. Native callback delivery remains unverified.

# Production SMS release checkpoint — 2026-10-15

Branch: `codex/retell-sms-production`, isolated from production commit `5c138f1`.
Checkout: `work/wholesale-sms-production` beside `work/wholesale-launch-prep`.

## Completed
- Production SMS_LIVE_ENABLED set false and redeployed: dpl_6dchgdYjKXBu4LhuLaeKfYdyfoLZ READY, production aliases assigned; code remains 5c138f1 until this SMS release is deployed.
- Ported consented-form queue, authenticated worker, CRM chat receipts, reply/STOP follow-up and SMS history only. No collector or general campaign activation.
- 143 targeted Python tests pass; frontend production build passes.
- Applied retell_form_sms_production to production Supabase dvzhzlipbwzzcliujzyz. Queue empty, scheduler enabled=false, cron inactive, tick requested=false.
- Production migration preserves private schema permissions and shared seller-outreach locks/call+SMS limits; does not overwrite claim_twilio_sms with older rehearsal behavior.
- Transactional SQL rollback verification passed: carrier reply, duplicates, phone-wide STOP, late reply, START and completed-task preservation. No messages sent.
- Fixed pinned numeric Retell agent version serialization, including V0, with tests.

## Remaining before owner test
1. Deploy this isolated code with production environment; do not promote full launch-prep branch.
2. Connect production Retell SMS credential and scheduler bearer securely. Prior credential approvals were rehearsal-only; production browser credential access/storage requires specific approval. Production scheduler needs no Vercel bypass.
3. Publish a production Retell agent version with production callback; preserve rehearsal V0. Verify signing/authenticated worker with no-send probes.
4. Verify exact public intake endpoints for hilltophome.co and thejaysdallas.com/sell. Sending remains OFF.
5. Confirm Retell actual chat callback phone schema and TwiML redirect compatibility before enabling replies. Existing redirect is experimental OFF; do not claim native provider acceptance.
6. User prefers to enter their number in actual forms, not in chat. Identify their explicit test submission before finite recipient allowlist. Never infer owner from latest lead. Test both forms separately; shared 24h cooldown and prior accepted-chat guard require a bounded test procedure, not global bypass. Do not clear DNC for a second test.
7. Perform controlled delivery/reply/STOP acceptance only after checks. SMS dispatch due at 60 seconds, scheduler 10-second cadence plus provider delivery latency. Keep calls off; no general sending.

Original bulk progress remains in wholesale-launch-prep/docs/START-HERE-NEXT-CHAT.md. Cumulative PropStream cap $50 unchanged.

## Live no-send checks
Production /api/health returned200; /api/forms/hilltop-home-co returned200 active=true. Unauthenticated worker probe returned503 because production scheduler authentication is not configured yet (closed, not a successful connection test). Hilltop public client posts to /api/get-offer; its server-side destination still requires verification. Jays sell page loads, server submission destination not yet established. Do not equate public availability with end-to-end submission evidence.

## Controlled owner acceptance procedure
Keep all sends off until configuration and signed callback checks pass. Have owner identify their own website submission, then set a finite allowlist to that exact phone. Do not guess from recency. Prepare each site separately; currently a prior accepted chat and 24-hour contact cooldown prevent testing the same phone twice immediately. Build an explicit owner-test exception scoped to submission ID and expiring authorization if needed; do not globally disable suppression/cooldowns or erase consent history. Verify first receipt, due+60sec handoff, provider receipt, handset arrival, reply task and STOP suppression; turn switches off again. Carrier latency is measured, not guaranteed exactly60seconds.
