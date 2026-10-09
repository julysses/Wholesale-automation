# Hilltop Home Co. — 30-day production launch plan

Reviewed: September 28, 2026, America/Chicago. Planning baseline: Day 0 = September 28; Day 30 = October 28, 2026. Exact launch date and launch channels await Julio's confirmation.

**Current decision: NOT READY for paid lead generation.** The website is reachable and the CRM application responds, but reliable lead capture, owner notification, database protections, and recovery have not been demonstrated end to end. This is a review and execution checklist, not certification that fixes have been deployed.

**Recommended launch scope:** one seller acquisition funnel, dependable CRM intake, owner alerts, personal follow-up, appointments, offers, buyer matching, and closing tracking. Add automated seller SMS only after its own acceptance gates pass. AI voice, bulk outbound campaigns, enrichment, and external calendar sync are separate optional releases. A fully automated launch must pass those additional gates before activation.

## 1. What was verified today

| Item | Evidence | Meaning |
|---|---|---|
| Website and HTTPS | `https://hilltophome.co` returned 200; HTTPS `www` returned 301 to the apex, without bypassing certificate validation; homepage rendered in browser | Prior website/HTTPS problems are cleared for these checks; form submission is not proven |
| Public website contact number | Footer displays `(214) 555-0100`, linking to `tel:+12145550100` | Confirm and replace the placeholder before traffic is purchased |
| Website form | Public JavaScript posts to same-site `/api/get-offer`; client validation says SMS consent is required | Trace the Netlify endpoint through to the CRM; allow an inquiry without mandatory marketing/text enrollment |
| Privacy page | Published policy lists SMS STOP/HELP, service providers, and retention | Review accuracy against actual configuration and provider requirements; publication alone is not approval |
| CRM process | `/api/health` returned 200; unauthenticated scoring-status route returned 401 | Process responds and this protected route rejects anonymous access; health endpoint does not check database connectivity |
| Form configuration | Initial read-only request timed out at 30 seconds; a longer check returned HTTP 404, `Form not found or inactive`, after 39.54 seconds | Intake remains a launch blocker; source catches database lookup exceptions and returns 404, so missing/inactive config versus failed queries is unresolved |
| Database | Supabase lists project `dvzhzlipbwzzcliujzyz` as ACTIVE_HEALTHY, but SQL and migration-history inspection timed out | Provider status is not evidence that application queries, policies, or schema are working |
| Production version | Vercel lists production deployment `dpl_GfuX95BKyZ2G1cjaYpsZoSqBsb5s`, READY, commit `2d67db1` | PR #7 repairs are in the listed production deployment |
| Facebook follow-up change | PR #8 remains OPEN at `dfdb630`; its recorded CI checks succeeded and preview is READY | Facebook owner-alert and affirmative-consent changes are not in the production branch |
| Alert failure handling | Current `web/api/lead_forms_api.py` ignores `SMSClient.send()` result; failed DNC lookup defaults to not suppressed | Source-confirmed defects to repair and test before enabling automated SMS |
| After-hours alerts | Owner and seller alerts use the same SMS client with allowed-hour restrictions | An always-on internal alert route or reliable deferred recovery is needed |

Previous September acceptance reported 230 backend tests, 88 frontend tests, signed-in CRUD/pipeline/admin checks and a passing lint regression gate. These are historical results, not tests rerun today. Historical provider-credential gaps, role checks, migration gaps, and buyer counts may have changed; they remain unverified until refreshed. Do not reuse historical zero-buyer counts as current facts.

## 2. The production process we need to prove

Facebook ad or Page link → website form OR native Meta lead form → durable receipt → validated/deduplicated CRM lead with source and consent → assigned owner and alert → personal contact → qualification and appointment → reviewed offer → signed contract and title opening → buyer matching and disposition → closing → actual revenue and campaign attribution.

Every lead must have an owner, current stage, next action, and due time. A submitted lead must remain recoverable if scoring, texting, or notification fails. A success screen must mean the inquiry was durably accepted, not merely that an external request was attempted.

Two separate inbound routes need separate testing:

- Website: browser → Netlify `/api/get-offer` → identify and verify actual server destination → CRM submission and lead. The destination behind Netlify was not visible in this review.
- Native Meta forms, if selected: Meta lead event → verified webhook → lead retrieval → deduplicated CRM lead → owner notification. PR #8 improves this route but is not itself launch acceptance.

## 3. Open-item checklist

Status legend: **Confirmed gap** = observed today in UI/source; **Unverified** = evidence still required; **Optional** = may be deferred only when disabled and excluded from launch. All unchecked rows are open. Owners are proposed assignments: Codex = technical implementation/testing, Julio = business decisions/operations, specialist = designated title/legal/provider support.

### A. Essential before paid traffic

| Done | ID | Open item / status | Owner | Due | Acceptance evidence |
|---|---|---|---|---|---|
| [ ] | A01 | Confirm launch date, website vs native Meta form, service area, follow-up channels and staffing — Unverified | Julio | Day 2 | Written scope, primary owner, backup owner, response hours and capped ad budget |
| [ ] | A02 | Replace placeholder website phone and reconcile contact identity — Confirmed gap | Codex + Julio | Day 3 | Approved number on website, both relevant Facebook Pages and provider; inbound call/voicemail routing demonstrated with an authorized test |
| [ ] | A03 | Diagnose database/query timeout and public form lookup — Confirmed failure of acceptance check | Codex | Day 4 | Active form config returns within agreed target, database queries work, failures return honest status; inspect server logs before assuming missing data |
| [x] | A04 | Verify Netlify-to-CRM intake contract — Accepted October 8 | Codex | Day 5 | Hilltop and each Jays intent verified against actual public endpoints, validated fields/disclosure, linked receipt/lead/task/owner alert and matching processed acknowledgement; local upstream failure/reload/retry and production exact replay accepted. Public intake requires no privileged browser credential. See October 8 checkpoint for exact deployments, receipts and tests. |
| [ ] | A05 | Decouple offer inquiry from mandatory SMS enrollment — Confirmed gap | Codex + Julio | Day 5 | Offer request works unchecked; no seller SMS without affirmative consent; exact consent text/version, source and timestamp retained; policy matches actual use |
| [ ] | A06 | Isolate test environment and reconcile database protections — Unverified, historical gate | Codex | Day 7 | Separate test data/project; inspect actual policies and both migration histories; validate public-intake protection; anonymous direct writes denied while approved API intake works; backup and rollback recorded |
| [ ] | A07 | Owner notification and assignment — Confirmed gaps in alert path | Codex + Julio | Day 10 | Every accepted lead creates a durable owner task; alert reaches owner within proposed 60 seconds, including nights/weekends; backup channel and escalation work on alert failure |
| [ ] | A08 | Durable processing and failure recovery — Unverified | Codex | Day 12 | Terminate processing after receipt; lead is recovered without lost data or duplicate outreach; retries have bounded attempts, visible failed status and an assigned operator |
| [ ] | A09 | Deduplication and repeat inquiries — Partially implemented, unverified end to end | Codex | Day 12 | Double click, network retry and repeated provider event do not create duplicate sends; repeat seller inquiry remains visible and actionable; normalize phone/address carefully |
| [ ] | A10 | Operator access and privacy boundaries — Unverified | Codex | Day 14 | Fresh admin, approved non-admin, unapproved and anonymous sessions show intended access; no privileged keys in browser; admin tools/data denied appropriately |
| [ ] | A11 | CRM acquisition workflow — Historical acceptance only | Codex + Julio | Day 17 | Lead → qualification → appointment → analysis → offer → contract → buyer stage works in current build; saves survive reload and failure states are visible |
| [ ] | A12 | Acquisition SOP and ownership — Unverified | Julio | Day 17 | Response script, qualification questions, conservative comp/repair review, offer approval authority, next-task rules and after-hours coverage rehearsed |
| [ ] | A13 | Contracts, title and closing process — Unverified | Julio + title/legal specialist | Day 20 | Confirm title partner, contract/assignment templates, applicable disclosures, earnest-money process, deadlines, inspection/access and closing responsibilities |
| [ ] | A14 | Buyer disposition process — Unverified | Julio | Day 20 | Current buyer inventory reviewed; proposed minimum 10 relevant vetted buyers or a named disposition partner, documented buy boxes/contact permission; sample deal can reach qualified buyers through an approved channel |
| [ ] | A15 | Meta account and campaign readiness — Unverified | Julio + Codex | Day 21 | Correct Page/ad account ownership and access, billing/spend cap, account quality, applicable housing category, geography, ad/form/privacy links and destination verified in Ads Manager |
| [ ] | A16 | Attribution and conversion accuracy — Unverified | Codex | Day 21 | UTMs persist into CRM; one successful intake yields one intended Lead conversion; failed validation does not; test Pixel installation and deduplicate browser/server events if both exist; exclude QA activity from reporting |
| [ ] | A17 | Monitoring, backups, restore and rollback — Unverified | Codex + Julio | Day 23 | Alert on intake/query failures and stale unprocessed receipts; named on-call owner; restore rehearsal in staging; provider/ad pause and deploy rollback steps documented |
| [ ] | A18 | Production rehearsal and sign-off — Open | Codex + Julio | Day 28 | Complete acceptance matrix below, close critical defects, check current deployment/logs and obtain business go/no-go |
| [ ] | A19 | Controlled launch and daily reconciliation — Open | Julio + Codex | Days 29–30 | Approved capped spend, monitored lead flow, source-to-CRM counts reconciled and no unexplained losses; scale only after review |

### B. Additional gates for selected automation channels

| Done | ID | Open item / status | Owner | Due | Acceptance evidence |
|---|---|---|---|---|---|
| [ ] | B01 | Review and release PR #8 for native Meta intake — Confirmed undeployed | Codex | Day 10 | Review exact head, update tests, signed event + retry acceptance, then merge/release through normal process; owner alert occurs once for each new lead |
| [ ] | B02 | Meta integration credentials and permissions — Historically missing, currently unverified | Codex + Julio | Day 10 | Correct app/Page/form, lead retrieval access, leadgen subscription and signing verification; signed Meta test event reaches CRM; token expiry/renewal owner recorded |
| [ ] | B03 | SMS sender and carrier approval — Unverified | Julio + Codex | Start Day 1; pass by Day 14 | Select provider and sender; complete applicable registration/verification; approved status and controlled device receipt. If approval is late, launch with this channel disabled |
| [ ] | B04 | SMS consent, suppression and failure behavior — Confirmed source gaps plus unverified integration | Codex | Day 14 | STOP updates shared lead/buyer suppression and cancels future sends; HELP works; unknown DNC/consent lookup blocks seller send; false/absent consent blocks; dry-run/accepted/delivered/failed states remain distinct |
| [ ] | B05 | SMS scheduling and replies — Unverified | Codex + Julio | Day 14 | Seller send-hours policy validated for chosen use; deferred messages recover once; owner alerts independent; replies create a visible owner action; no automatic resend after uncertain delivery |
| [ ] | B06 | Email delivery, replies and unsubscribe — Unverified | Codex + Julio | Day 17 | Select implemented SendGrid/Mailgun path; authenticated sending domain, authorized receipt, bounce/failure visibility, reply routing and suppression verified |
| [ ] | B07 | AI voice initiation, consent, handoff and callbacks — Optional, unverified | Codex + Julio | Day 21 or defer | Prove actual supported call-initiation route, appropriate consent/disclosures, controlled recipient, human handoff, recording/transcript access, signed Retell callback, duplicate protection, timeout and parked-job recovery |
| [ ] | B08 | Bulk imports/enrichment/scoring — Optional, known scope risk | Codex | After launch or separately gated | Explicit job scope/cost cap and cancellation; import must not unexpectedly score full historical backlog or trigger outreach; use approved cohorts only |
| [ ] | B09 | External calendar sync and Development workspace extras — Optional | Codex | After launch unless needed | Calendar integration implemented and round-trip tested before promised; otherwise manually manage appointments. Development cold-load/import-export and native date clearing verified if used |

A B-row becomes launch-critical whenever that channel is enabled. Deferral means it is explicitly disabled, excluded from public promises, and supported by a tested manual alternative. Personal follow-up still requires an appropriate contact basis and suppression handling.

## 4. Work plan and dependencies

| Window | Work package | Exit condition |
|---|---|---|
| Days 1–7: Sep 29–Oct 5 | Confirm scope and business number; locate website source/Netlify settings; diagnose database/form; fix consent flow; trace website receipt; begin sender approvals; establish staging/security rollout | Reliable website intake into test CRM, documented production repair path, contact details corrected |
| Days 8–14: Oct 6–12 | Owner tasks/alerts, recovery/deduplication, access checks; complete selected Meta/SMS integrations and STOP handling | No lost/duplicate controlled leads; all enabled channels have verified suppression and failures |
| Days 15–21: Oct 13–19 | Rehearse acquisition and disposition; contracts/title readiness; buyer roster; tracking and Ads Manager checks; optional voice/email only if selected | A complete simulated seller-to-closing journey with owners and measurable attribution |
| Days 22–28: Oct 20–26 | Failure drills, backup/restore, final fixes, release validation, production controlled test and go/no-go | All essential and selected-channel gates passed; no unresolved critical defects |
| Day 29: Oct 27 | Freeze nonessential changes; confirm staffing, numbers, spend cap and pause controls | Launch checklist signed and support ready |
| Day 30: Oct 28 | Activate the approved small campaign; watch every new lead, task, alert and response | Reconciled intake and stable follow-up before any budget increase |

Critical path: A03 database/form → A04 real intake → A07/A08 alerts/recovery → A11/A12 acquisition → A18 rehearsal → A19 launch. Sender registration and account review start early because third-party turnaround may exceed the schedule. Posting for 30 days is preparation, not evidence that this path works.

## 5. Acceptance matrix — required evidence, not just checkmarks

Use isolated staging and controlled contact details. Production provider sends/calls require Julio's explicit recipient/channel authorization before execution. No production submissions, calls, texts, emails, ads or schema changes were performed in this review.

| Scenario | Pass condition |
|---|---|
| Website happy path, phone and desktop | 1 durable receipt, 1 linked lead, correct source/answers/consent, 1 owner assignment, accurate confirmation screen |
| SMS unchecked | Inquiry accepted; no seller SMS; owner receives task/alert |
| Invalid input | Clear field errors; no false success and no downstream sends |
| Double submission / provider retry | Idempotent processing; no duplicate seller message; repeat inquiry auditable |
| Database outage | Honest failure or durable queued acceptance; no lost lead or false success; operator alerted |
| Notification/provider outage | Lead remains actionable; failed/unknown status retained, backup alert and controlled recovery |
| After-hours/weekend lead | Internal owner notification/task still recorded; seller channel follows approved schedule and retries once when eligible |
| STOP / existing DNC / DNC lookup failure | Seller/buyer automation suppressed; future sequences blocked; internal owner workflow retained |
| Invalid webhook signature | Rejected without creating a lead or sending anything |
| Slow/duplicate/interrupted callback | Receipt persisted; duration within host/provider limits; recovery reconciles partial side effects before retry |
| Real access roles | Non-admin cannot administer; unapproved/anonymous cannot view private records or write directly to protected intake tables |
| Acquisition and disposition | Saved appointment, reviewed analysis, offer, contract stage, buyer match and closing tasks survive reload |
| Attribution | QA submission maps to correct campaign; failure not counted as conversion; browser/server duplicates eliminated if applicable |
| Restore / pause | Restore completed in staging; operator can pause ads and selected outbound jobs without discarding pending inbound leads |

Proposed operating targets, to approve in A01: internal alert within 60 seconds; first personal attempt within 5 minutes during covered hours; after-hours leads triaged at the next staffed opening; every open lead has an owner and next task. During controlled rehearsal, require 100% accounted-for receipts and zero unintended sends. Targets are not measured current performance.

## 6. Daily operating rhythm after launch

- Start of day: reconcile previous day's website/Meta receipts to CRM leads, inspect pending/failed jobs and overdue tasks, verify phone/inbox coverage.
- During covered hours: work new inquiries first; log contact outcome, seller needs, appointment/offer status and next action. Review HOT classifications rather than accepting AI output as an offer decision.
- End of day: reconcile all new inquiries; review spend, valid leads, contact rate, appointments, offers, contracts and closings; assign every outstanding follow-up.
- Weekly: review lead quality by source, buyer coverage, provider failures, suppressed contacts and actual economics. Do not increase spend based only on clicks or form counts.

Metric definitions: valid lead cost = ad spend / valid nonduplicate inquiries; contact rate = contacted leads / valid leads; appointment rate = appointments / valid leads; contract rate = contracts / valid leads; closed-deal acquisition cost = attributable ad spend / closed deals. Show counts beside rates; use matching cohorts when assessing conversion. Set dollar limits with Julio instead of assuming profitable targets.

Pause new ad spend for lost/unreconciled leads, broken intake, unintended messages, failed suppression, or inability to provide coverage. Preserve inbound records, disable the affected send path, assign recovery, and retest before resuming. Small volume does not excuse broken capture or consent.

## 7. Go/no-go checklist

- [ ] All A items needed before activation have evidence; A19 launch monitoring is staffed and ready.
- [ ] Every enabled B integration passes; deferred channels are disabled with a documented fallback.
- [ ] At least one complete controlled production inquiry passes after the final release, plus staging failure scenarios.
- [ ] Current deployment, database migration state, provider approvals and access roles verified.
- [ ] No unresolved critical security, data-loss, suppression, false-success or duplicate-send defects.
- [ ] Business phone, public claims, privacy/contact text and actual operating process agree.
- [ ] Julio approves spend cap, coverage, launch scope and pause conditions.

If these are not met by October 28, use a narrower tested launch scope or move the launch. Do not activate an untested intake route simply to meet the date.

## 8. Resume checkpoint and progress log

**Completed September 28:** located and pulled current repository; inspected production source and PR #8; verified website HTTPS/browser rendering and placeholder number; checked health/auth boundaries and deployment history; attempted read-only database inspection and observed delayed form-config HTTP 404; reviewed public client consent behavior; created this plan.

**First next action:** restore/verify A03 Supabase connectivity (production logs show upstream HTTP 522), then identify the website repository and Netlify `/api/get-offer` handler for A04. Review candidate branch `codex/hilltop-launch-hardening`; source fixes are prepared but not production acceptance. Do not infer the website's backend destination from branding or from the separate CRM form endpoint.

**Decisions pending from Julio:** exact ad date; website vs native lead form (or both); personal vs automated follow-up; confirmed business number; primary/backup owner; ad spending cap; authorized provider test contacts when tests are staged.

**Technical handoff:** repository `julysses/Wholesale-automation`; default branch `claude/ai-wholesaling-agency-KkDF1`; production reviewed at `2d67db1`; open Facebook PR #8 at `dfdb630`; Supabase project `dvzhzlipbwzzcliujzyz`. Existing untracked `docs/deployment-vercel 2.md` was left untouched. Plan is tracked at `docs/hilltop-30-day-launch-plan.md` on branch `codex/hilltop-30-day-launch-plan`, separately from production. Production code and PR #8 were not changed by this review.

Update this file after each work session: item ID, date, result, evidence, commit/deployment, unresolved issue and next exact action. Mark complete only when acceptance evidence exists. Refresh the user-facing output copy from the tracked repository plan so the two stay aligned.

| Date | IDs | Result | Next action |
|---|---|---|---|
| Sep 28 | Baseline | Review and plan complete; production readiness remains open | Diagnose A03; trace A04; confirm A01/A02 decisions |

## 9. Evidence and reference links

- [Hilltop website](https://hilltophome.co/) and [privacy policy](https://hilltophome.co/privacy-policy): browser-read September 28; live footer number and consent UI reviewed.
- [Published form client](https://hilltophome.co/_next/static/chunks/89-6b11c7272e4e962e.js): `/api/get-offer`, required-SMS-consent validation, and conditional Lead event code. Presence of event code does not prove Pixel initialization or delivery.
- [Open Facebook PR #8](https://github.com/julysses/Wholesale-automation/pull/8): current state and recorded checks inspected September 28.
- [Production source: intake](https://github.com/julysses/Wholesale-automation/blob/2d67db1a5d5524771cec02a2c1e4c40d553aa452/web/api/lead_forms_api.py), [SMS](https://github.com/julysses/Wholesale-automation/blob/2d67db1a5d5524771cec02a2c1e4c40d553aa452/tools/sms_client.py), [health](https://github.com/julysses/Wholesale-automation/blob/2d67db1a5d5524771cec02a2c1e4c40d553aa452/web/app.py).
- [Twilio A2P registration](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc) and [messaging policy](https://www.twilio.com/en-us/legal/messaging-policy): use chosen-provider requirements for registration, affirmative consent, sender identity and opt-out acceptance; documentation reviewed September 28. Do not treat existing code comments as legal guidance.
- [TREC current rules](https://www.trec.texas.gov/agency-information/rules-and-laws/trec-rules): validate applicable equitable-interest disclosures and contracts with the transaction professional before use.
- [Meta special-category help](https://www.facebook.com/business/help/1198401317374558): confirm applicability and current account requirements in Ads Manager; Meta account configuration was not inspected in this review.

Limits: no new full regression run, signed-in CRM acceptance, Meta account audit, provider round trip, migration rollout or production form submission today. Database contents and current provider credentials remain unverified. Read-only timeouts are diagnostic findings, not a root-cause diagnosis.


### September 28 implementation update

- A03: production runtime logs confirmed upstream Supabase HTTP 522; database outage was incorrectly mapped to form-not-found. Candidate fixes error reporting and redundant lookup. Connectivity is still unresolved.
- A07/B04: candidate saves in-app notifications before texting, blocks seller sends on uncertain suppression, and records failed/unknown/dry-run outcomes. Owner assignment, external after-hours delivery and live STOP synchronization remain open.
- B01: PR #8 code incorporated into the hardening candidate, not deployed.
- B03: missing default Twilio SDK added to deployment requirements with a dispatch contract test. Sender approvals and real delivery remain unverified.
- Validation: 251 backend and 88 frontend tests passed; build, lint regression gate and frontend audit passed. See `docs/hilltop-launch-hardening.md`; no checklist item is closed solely by mocked tests.
- Resume branch: `codex/hilltop-launch-hardening`. Resume with upstream database recovery, isolated acceptance and release review. The earlier plan-only branch is retained for history.


### October 8 — deal handoff acceptance update

A11 technical progress: recoverable deal creation and version-checked edits deployed ef19e5b (READY dpl_Datg7dFJTMnZtztfFPUV5JKgbTiq; CI37858574421success). A13/A14 recording safeguards now expose owner, buyer, earnest money, inspection/closing dates, title contacts and HTTPS document links; saves atomically maintain assigned deadline review tasks. Required stage evidence is checked; recording a link does not validate signatures or open title. Full regression620backend/127frontend tests, build and lint gate pass. Actual controlled dummy save/reload/task/cancel confirmed; QA deal and tasks retained cancelled, active deals0, no new provider sends. See tasks/final-launch-verification-20261008.md for exact IDs and screenshots.

Full A01–A19/B01–B09 scope remains open wherever required evidence is incomplete. A11 business rehearsal, A12SOP, A13title/contracts/earnestprocess and A14vettedbuyerpermission are not complete solely from technical persistence. Next technical audit A16 QA exclusion, attribution and conversion accuracy; provider/KYC/worker/opt-out/nativeMeta and staffing/spend/businessgo-no-go gates remain pending. Earlier September baseline observations above are historical; current decision remains no final launch certification.

### October 8 — business reporting acceptance update

A16 QA exclusion accepted in production: confirmed internal tests are reversibly classified and excluded from Dashboard, Reports, workflow milestones, precision/stack metrics and legacy funnel totals. Actual signed-in screens and independent SQL agree: 17349 retained leads, 16 confirmed exclusions, 17333 reportable leads; no actual closed deals or fees. Two test analyses remain accessible in operational history. Completed appointments no longer count as contracts; multiple estimates no longer inflate lead counts. Frontend132tests/build/lintregression and exact releaseCI passed. Migration20261008234456 also aligns legacy consumers, with isolated rollback proof and production SQL verification. See tasks/final-launch-verification-20261008.md for exact release/evidence.

A16 remains open for UTMs, Pixel installation and exactly one conversion per durable successful intake. A09 follow-up audit must address stable website request references and lost acknowledgements before claiming retry deduplication. Full provider, business and final go/no-go acceptance remains open; calling and nurture remain disabled.

### October 8 — public intake retry foundation accepted

A09/A16 technical progress: service-only reservation of an immutable inquiry UUID deployed eda286e1; same-reference retries return the original processed receipt, changed-input reuse is rejected, and distinct inquiries from the same contact remain separate. Fullbackend627tests and releaseCI passed; isolated/production rollback proofs and actual controlled public POST/replay/conflict verified. One lead, one follow-up task and one owner notification with provider-accepted email; no seller SMS. Controlled QA retained, reporting-excluded, taskcancelled. Browser forms and website proxy routes still need to supply/preserve the reference and verify the acknowledgement, so website retry acceptance remains open. Source audit also found Hilltop Pixel components not mounted; full attribution/conversion evidence remains required.

### October 8 — Hilltop website retry acceptance

Hilltop production02163cb published successfully as Netlify6ac831a9706414000854f76f. Immutable browserpendinginquiry/reload recovery and matching processed receipt are wired through websiteproxy. Actual livebrowser submission, confirmedack, clearedrecoveryafterreload and exactproxyreplay verified: oneinquiry/lead/task/ownerappnotification, owneremailprovideraccepted, optionalSMSfalse/noSMS. CurrentQA excluded and taskcancelled, evidence retained. ExistingGooglefont-loader buildfailure repaired with sameInterfont bundledlocally; actualcorrecteddeploypassed. Tests/typecheck/build and localfailedack/reload/retry accepted. Jaysintentforms andCRMLeadForm still require reference wiring; full UTMs/Pixel/conversion/provider/businessgo-no-go scope remains open.

### October 8 — Jays intent forms accepted in production

Jays main63ecf88 published Netlify6ac83454ac2e450008d73b2a. Actual live contact(email-only), seller(optionalSMSunchecked), buyer and financing independently created their correct inquiry/lead, one assigned follow-up, one owner notification and SendGrid-accepted owner email with provider receipt. Exact same-reference website replays did not duplicate those records; confirmed recovery cleared across reload/navigation. Original consent evidence preserved; non-seller inquiries did not enable seller outreach. Four explicit QA leads reversibly excluded/taskscancelled, auditretained; reportable17333, calls0/SMS9 unchanged. See checkpoint for receipt IDs and screenshots. Narrow Saving-state text correction8595891 published Netlify6ac8361ac15e85000833a47a. Freshmailboxreceiptquestionpending. CRM public LeadForm remains legacy/noUUID/recovery/strictack and is next. Attribution/Pixel/conversion, provider opt-outs/voice, monitoring/recovery, and full business go/no-go still open; this is not final launch approval.

### October 8 — CRM public-form recovery accepted

CRM public LeadForm now saves immutable UUID/answers/disclosure/UTMs before dispatch, recovers locked answers across reload, explicitly retries the same payload, and requires matching processed receipt before success/redirect. Storage failures and unfinished/wrong acknowledgements fail closed; first pre-write validation can release editing while an uncertain retry remains protected. Full frontend140tests/build/lintgate and exactreleaseCI37865846544passed. Productioncbd6a703 deployedREADYdpl_ARXfbnvdP8M1v3p1FXoYhM3zgYfK. Actual controlled live submission/replay/conflict/reload accepted: receipt6866830c-cdd5-42e9-9362-e93018c14463, one lead/task/adminnotification, SendGridowneremailaccepted, SMSunchecked/noSMS. QAexcluded/taskcancelled/auditretained; reportable17333 unchanged. A04checked; A07/A08 notification crash/backup recovery and A09native/provider-repeat acceptance remain open. Next durable alert recovery, followed by first-touchattribution/Pixel/conversion and full provider/business launch gates. Calling/nurturedisabled; no final go/no-go.
