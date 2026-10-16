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
- [ ] Deploy current application and inspect authenticated Daily Lists.
- [ ] Reconcile/transfer existing source and PropStream receipt graph without duplicating leads, requests or spending.
- [ ] Verify a matched batch in production including ownership, task and held contact history.
- [ ] Connect scheduled ingestion to production after acceptance; observe a genuine source run.

Do not activate SMS, order new traces, erase suppression history, copy credentials, or promote the collector branch wholesale. All source collection starts disabled in the production migration. Historical raw data expiry and missing provider delivery evidence remain explicit review items.

Weekly monitoring retains expired raw evidence and contacts for explicit maintenance review; it no longer purges them as a side effect. A transient connector request error was reconciled against migration history and absent columns before applying successfully. No data transferred or sending enabled. Live rehearsal inventory: 79 properties, 77 trace requests, 481 contacts, 8 runs, 105 raw payload batches, 49,537 source records and 81 review events.
