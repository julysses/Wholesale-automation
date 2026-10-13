# Production readiness — October 13, 2026

**Decision: NO-GO for the full automated launch.** Passing tests and a ready preview are not production acceptance. Existing production is unchanged. Draft PR #20 remains the release candidate: https://github.com/julysses/Wholesale-automation/pull/20 .

## Verified this session

- Launch branch synchronized and SMS/date fixes pushed as722c761. Preview deploymentdpl_DXZvAXvhrV6smH2MqcFm73BCi1tv is READY for that exact commit; runtime configuration contains rehearsaltbhwxgfzbiaqjurghntj, not productiondvzhzlipbwzzcliujzyz.
-837backend tests passed for722c761. Final full197frontend tests passed after legacy approval recovery; build and lint regression passed (146existing lint findings; bundle-size warnings remain).
- Frontend production dependency audit:0known vulnerabilities. This is npm audit coverage, not a complete security certification or a Python dependency audit.
- Production /api/health and /api/forms/hilltop-home-co returnedHTTP200 onOctober13. This is read-only availability evidence, not a new website submission or owner-alert delivery test.
- Earlier today: authenticated rehearsal service reads, synthetic land save/reload and one immutable valuation receipt verified independently in SQL. Prices/stage/contact remained unchanged. See checkpoint for fixture IDs and exact evidence.
- Current production SQL for the authorized0100test destination shows2delivered outbound receipts,0inboundSTOPreceipts, and0of21matching lead records markedDNC/suppressed in the checked fields. The0100STOPtest remains pending; this is not proof of a suppression defect.
- WARM route now rejects custom SMS content; standard informational follow-up only. Non-Twilio SMS dispatch disabled until equivalent safeguards exist. No seller messages sent.

## Required completion sequence

| Gate | Current state | Next action / acceptance evidence | Responsible |
| --- | --- | --- | --- |
| Stable rehearsal session | Verified signed in October 13 | Continue using the stable branch origin | Codex |
| Offer review UI | Synthetic save/reload/approve/revoke passed; three events independently verified in SQL | Property-change rejection and retry recovery in browser; separate human operator acceptance | Codex + Julio |
| Final offer delivery | Incomplete | Freeze final channel-specific recipient/from/body/footer/unsubscribe envelope; require exact human approval; recheck consent/DNC/quiet hours/caps at queue and dispatch; durable single-attempt provider receipts and uncertain-outcome recovery | Codex; Julio approves real terms |
| Lot routing / valuation | Core SQL/concurrency tests and one browser valuation save passed | Synthetic review → score → handoff → correct assigned inbox → receipt → stale/hold/reaffirm; lost-response/concurrent UI cases; reassignment recovery | Codex |
| PropStream tracing | Browser account verified; latest authorization is existing $50 total balance only | Quote each eligible batch; cumulative spend plus uncertain reservations must stay within $50 and current balance; no refill/upgrade. Reconcile results before retracing; no API adapter assumed | Codex |
| Official collectors | User confirms no operating schedule; rebuilding. Dallas endpoint corrected in rehearsal; sources remain disabled | Follow collector-rebuild.md; complete supervised collection and verified delivery before scheduling | Codex |
| Model scoring | Default disabled; live calibration incomplete | Current-model evidence calibration, receipt recovery and runtime bounds | Codex with authorized account/budget |
| Owner digest / monitoring | Default disabled; actual scheduling/delivery unverified | Connect scheduler, verify owner delivery, overdue/failed receipt routing and independent missing-worker alerts | Codex + Julio receipt confirmation |
| Buyer workflow | Incomplete | Verified top3cash buyers by area/price/history, wholesaler exclusions and actual outcome recording | Codex + Julio business criteria |
| Twilio / SendGrid | Earlier controlled delivery confirmed; remaining acceptance open | Confirm relevant STOP/refusal state and secondary-email unsubscribe; verify receipt callbacks and suppression across workflows | Codex + Julio controlled destinations |
| Retell / Meta | Accounts connected historically; live acceptance open | Audit approved Retell agent/version/tools/knowledge, controlled call/handback; native Meta lead and matching consent callback acceptance | Codex + Julio |
| Recovery / access | Rehearsal restored; complete evidence open | Auth/Storage/Edge restoration, second-role signed-in authorization, interrupted-worker recovery and operator procedures | Codex + Julio where separate identity needed |
| Operations observation | Required run history has not occurred |5clean supervised foreclosure runs per county and14unattended days, with delivery and incident evidence | Codex + operating owner over elapsed time |
| Production release | Not authorized by draft-only release scope | Review exact migration mapping/backup/rollback and coordinated API/UI rollout; obtain production release approval; repeat live intake/owner-alert and signed-in acceptance | Codex prepares; Julio approves release |
| Business go/no-go | Open | Confirm legal/title/disclosure process, staffing, permitted contact policy and spending authority | Julio |

The technical items above remain work to do, not merely credentials to enter. No launch date is promised before the observation window and required acceptance evidence exist. Do not enable outreach or remove the controlled recipient restrictions to make a readiness indicator pass.

## Resume

Stable preview: https://wholesale-automation-git-codex-dallas-de1768-julysses-projects.vercel.app

Detailed chronological evidence, migration mappings and synthetic fixtures: [launch checkpoint](dallas-collin-launch-prep-checkpoint.md). The older release-evidence file contains historical rows; use this checklist plus the latest checkpoint for current status. No production promotion has occurred.

## October 13 follow-up

- Current code af68671 verified READY as deployment dpl_9vUGWepiWnTVsYUvPNxyckX5w22b. Stable-origin offer rehearsal passed with synthetic records only.
- New offline collector preflight plus source correction: 22 targeted tests passed. Preflight is not a collection runner or a delivery receipt.
- Dallas source correction applied only in rehearsal; migration mapping and next steps are in the checkpoint. Production remains unchanged.
- PropStream Legacy account shows $50 prepaid credit, 25,000 saves/exports, renewal November 1. No included 100-trace allowance confirmed. Latest user instruction authorizes using the existing $50, superseding the earlier free-only answer. No trace order or paid debit was submitted this session.

## October 13 resumed collector work

- Starting commit24357e0 verified READY as previewdpl_AY1fGsN9LUb5LgMuYe1ULBgYaavg. Stable rehearsal remains signed in; synthetic offer still shows version3/unapproved. No new offer decision made.
- Added local coverage-ledger enforcement and12regression cases;34targeted tests passed. It rejects complete claims without matching traversals and document review. Edge enforcement/delivery integration remains open.
- Dallas count drift479→490 prevented complete coverage. Collin164filtered entries were traversed once; document IDs, complete notice review and second traversal remain unverified. No ingestion or clean-run credit. See collector-coverage-ledger.md.
- No PropStream order, collector schedule, worker activation or production change. Existing release and observation gates remain open.


## October 13 — cumulative tracing authorization and direct outreach

- Owner clarified the objective: develop lawful direct outreach to newly sourced Dallas/Collin opportunities. See `docs/direct-outreach-operating-plan.md` for the acquisition-to-consent process, draft mail/form/SMS copy and campaign-specific legal/provider questions. No cold-list consent bypass added.
- Fixed daily-only spending protection with a service-only cumulative $50 cap across all providers and dates, including uncertain holds. Operator panel displays cumulative remaining funds; legacy API responses explicitly show total authorization unavailable. Database ledger cannot detect external PropStream spending; exact live balance/quote reconciliation still required.
- Local migration `20261013164454_list_trace_total_cap.sql` applied to rehearsal only as remote version `20261013165414`. Verified cap5000, committed0, remaining5000 cents; zero daily budgets, zero enabled sources, browser execution denied, service execution allowed. No paid requests or production changes.
- Validation: 14 budget/contact/total-cap tests; 4 tracing UI tests; TypeScript build check; full disposable PostgreSQL/TLS integration suite including real overlapping cumulative-cap reservations all passed. Two concurrent $30 requests with $0.50 already spent yielded one reservation and one total-cap rejection. No provider invoked. Test fixture foreign-key omissions were corrected before final passing run.
- Saved Codex heartbeat `wholesaleos-dallas-and-collin-collection`, daily05:00 America/Chicago, **PAUSED**. This is a saved schedule definition, not accepted operating collection. Activate only after durable delivery/worker/digest and release gates. Earlier statements that no scheduler definition exists are superseded; no active operating collector exists.
- Rehearsal Edge-function inventory was empty. All8source rows disabled, zero trace requests/budgets; only inspected database cron was inactive refresh-lead-retention. Source-scoped ingress deployment and exact ingestion receipts remain next blockers. Do not claim county-to-CRM automation works.
- Security advisor: no new cap-function finding. Open warnings remain for authenticated SECURITY DEFINER functions (`admin_set_user_role`, `admin_set_user_status`, `is_approved`), disabled leaked-password protection and insufficient MFA options; 23 informational no-policy RLS notices concern private/server tables. Review function authorization before changing intentional entry points. References: https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable ; https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection ; https://supabase.com/docs/guides/auth/auth-mfa . Advisor output alone is not an exploit finding.
- Next: verify preview UI cumulative display, deploy/accept rehearsal ingress, finish reviewed foreclosure manifests and authoritative tax-delinquency adapters, prove cross-source only-new selection and PropStream reconciliation, then controlled consent/STOP acceptance. Five clean supervised runs per county and14unattended days remain unfulfilled. Full automated launch remains NO-GO.


## October 13 — tax collectors and deployed ingestion shell

Implemented official-link tax ZIP fetcher, fixed-width Dallas/Collin parsers, integer-cent control reconciliation, bounded manifests, and scoped HTTP delivery with durable local retry journal. See `docs/county-tax-collectors.md`. Full archives yielded30,516Dallas and9,182Collin review candidates; all81batches validated. Counts are not verified new leads.10Python parser/security tests and23Node collector/preflight/coverage/delivery tests passed. Collin full fetch-discover-download-parse run passed with matching archive hash. Dallas full archive was downloaded and parsed; fetch-wrapper live check remains pending. No county records delivered yet.

Deployed rehearsal `daily-list-ingest` Edge version1, function2967097e-01a8-4559-8543-324ba0d85354, bundle2dc68bfca73dacb05537c284c135fc8d13c569d1c59f4581ad67aa82812e1f13. Body contains explicit hashed/scoped/expiring token authentication; platform JWT check is off to use that custom credential. Exact unauthenticated POST returned503ingest_not_configured, confirming fail-closed missing secrets. Sources remain disabled. Local CLI sign-in was requested because MCP cannot configure Edge secrets; owner reports browser sign-in, CLI still needs authorization. No production or live outreach change.

Private working evidence: `/Users/juliodominguez/Documents/Codex/2026-10-13/resume-wholesaleos-from-docs-start-here/work/county-sources/`. Dallas run68e93ec1-6e54-4c66-a96b-bd30035de6b7; initialCollin rune3616157-5607-494f-93fa-f06939b8f25a; verifiedfetchCollin run892910fa-9b11-4467-993a-d98ae083a8ac. Use only one Collin snapshot run for eventual delivery; preserve originals and replay exact payloads. Tax collectors intentionally leave account/property review incomplete.
