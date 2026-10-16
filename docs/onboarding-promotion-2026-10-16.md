# WholesaleOS onboarding checkpoint — October 16, 2026, 20:09 UTC

## Completed in production
- Migration 20261016195408_onboarding_promotion_receipts applied. Existing assigned follow-up tasks, including completed history, survive property association; missing lead owners are assigned to the approved default owner.
- Historical Collin promotion 2e91ac73-af2d-410b-860c-b7e249212408 committed at 2026-10-16 20:08:57 UTC in project dvzhzlipbwzzcliujzyz.
- 78 properties: 74 new CRM leads and four existing lead identities reused. All 78 have assigned owners and follow-up tasks.
- Preserved 77 original tasks; added one missing property follow-up. A separate daily summary task/notification covers the import.
- Preserved 77 completed PropStream requests and 481 contacts (146 DNC listed; 335 unknown). No channel eligibility granted.
- Preserved one complete historical run graph: 164 source records, 79 review events/signals, 156 aliases, 164 capture receipts and 420 page-extraction receipts, associated provider batches and external-job evidence.
- Source IDs mapped by source_key; embedded historical evidence and hashes remain unchanged. No source credentials copied.
- Source fingerprints unchanged immediately before commit. Exact transfer rehearsed in a production rollback transaction, then committed; repeat execution returned the same receipt without duplicate rows.
- All 128 pipeline tests passed. Live rollback QA passed ownership, task preservation, suppression, notifications, snapshots and private access. Live authenticated Daily Lists shows 78 associated properties, saved results, restored contacts and the assigned follow-up link.
- Collection remains disabled, daily tracing cap is zero, outreach remains false and SMS scheduler remains disabled. No new provider orders or contact messages sent.

## Evidence and files
Repository: /Users/juliodominguez/Documents/Codex/2026-09-28/make-sure-to-review-my-wholesale/work/wholesale-sms-production
Branch: codex/retell-sms-production
Repair commit: 2a12e58 (pushed).
Exact replay-safe transfer: pipeline/operations/promote_collin_20261016.sql. This is an already executed operations record, not a migration or automatic deployment step.
Private export and preparation: work/onboarding-promotion/ (Git ignored; JSON files mode 600). Production private staging holds source/target arrays and the four original existing-lead snapshots.
Source project tbhwxgfzbiaqjurghntj remains unchanged. Source run a0c09287-a888-4e8e-97ea-ab4964e5ab69 is historical, not a new successful collection.
App code deployment remains 8feb89b / dpl_ERRBVokFmZdqXUubwJn2umGNMQR4; current changes are database and operation records, with no frontend deploy required.
Security advisors have three preexisting function warnings and two additional expected INFO notices for deliberately private RLS tables without browser policies; no new WARN/ERROR. Direct browser-role access checks pass.

## Remaining launch gates — full goal still active
1. Correct stale operator instructions in WorkflowGuide.tsx and review SetupWizard claims. Do not tell operators to rerun migrations, imply CSV clears DNC, promise delivered SMS, or introduce unported offer workflows.
2. Reconcile the remaining historical Dallas and tax source inventory, excluding synthetic/test records. First promotion does not establish complete county coverage.
3. Review 85 unresolved Collin notices and the one property without a completed trace. Preserve evidence and existing contact restrictions; do not order paid work without checking the cumulative $50 cap.
4. Review the source automation configuration, point authorized ingestion at production after acceptance, and observe genuine source collection through CRM assignment/history. Never replay historical migrations blindly or claim a preflight is delivery.
5. Check Twilio ticket 29953072 and Retell ticket 65825 for meaningful changes. Do not send new support messages or activate outbound messaging without existing explicit authorization and delivery resolution.
6. Prove website and county onboarding, eligible outreach delivery, replies/STOP handling, CRM history, monitoring and operator acceptance end to end before declaring fully operational.

## Approval-review reconciliation
Automatic review rejected broad source/external receipt exports. Source configuration was restricted to id/source_key; external receipt keys were inspected and allowlisted. A later staging rejection flagged apparent Dallas records; exact joins proved all 77 members belong to Collin County, including two whose city is Dallas. The safer staged insertion verifies county membership for every request and succeeded. No unresolved approval blocker remains.

This goal turn made production progress. Goal remains active; no new spend or outreach.

