# Wholesale OS — launch completion roadmap (November 26, 2026)

Scope decision (user, this session): **AI calling (Retell) and nurture are deferred to v1.1.** v1 launches as public intake → CRM → owner email alerts → restricted/controlled SMS → manual follow-up → analysis → pipeline → reporting. Calling and nurture stay disabled and are not launch blockers.

Source of truth for evidence: `tasks/final-launch-verification-20261008.md`, `tasks/production-acceptance-20261007.md`, `docs/availability-monitor-repair-20261018.md`, `docs/hilltop-30-day-launch-plan.md`. Last repo activity: October 18, 2026. Status below is taken from those records; re-verify live state before acting on any item.

## 1. Where things stand

Accepted in production (evidence in the files above):
- Auth, approval gating and RLS repair; operational API routes protected; signed webhooks fail closed.
- Server-side resumable Claude lead scoring (17,333 reportable leads).
- Deal analysis save/history, durable pipeline handoff with deadline tasks.
- QA exclusion from business reporting (raw 17,355 / QA 22 / reportable 17,333 at last check).
- Public intake with immutable request references and replay safety: Hilltop site, Jays site (contact/seller/buyer/financing), CRM LeadForm.
- SendGrid email with signed callbacks (restricted to `julio@hilltophome.co`).
- Twilio SMS with signed callbacks (restricted to one authorized number; campaign verified).
- Native Meta lead intake, one lead and one task per test lead.

Not yet complete: see sections 3–6.

## 2. Critical path

```
Phase 0  Branch + deploy safety  ─┐
Phase 1  Release unreleased work ─┼─► Phase 3 Human acceptance ─► Phase 4 Business gates ─► Phase 5 Rehearsal + go/no-go
Phase 2  Attribution build       ─┘
```

Phases 0–2 are code/config work that can be done in a session. Phases 3–4 need the owner's hands or decisions and are the real long pole; start collecting those answers now.

## 3. Phase 0 — Branch and deployment safety (do first)

Problem: GitHub schedules the default branch `claude/ai-wholesaling-agency-KkDF1`, whose code is older than the live manually promoted release `e41e4a3`. Vercel still names that branch as its production source, and `vercel.json` has `git.deploymentEnabled=false` for it as a guard.

| # | Task | Acceptance evidence |
|---|---|---|
| 0.1 | Confirm what production is actually serving (Vercel deployment SHA, alias) | Deployment ID and SHA recorded |
| 0.2 | Reconcile: fast-forward default branch to the current verified application branch (`codex/twilio-live-integration` lineage) | Default branch contains live code; diff vs live is empty |
| 0.3 | Verify production still serves the same app after the push (health, `/api/config`, unsigned `/api/deals` = 401) | Check outputs |
| 0.4 | Only then remove the `vercel.json` deployment guard; point Vercel production source at the reconciled branch | Next push deploys the same code |
| 0.5 | Run the updated availability monitor on the default branch | Green run with attempt diagnostics |

Rule: do not remove the guard or deploy the old default branch manually until 0.2–0.3 pass.

## 4. Phase 1 — Release the unreleased work

| # | Task | Acceptance evidence |
|---|---|---|
| 1.1 | Update the native-Meta test DB mock for the new claim/finish protocol (known first resume step); run focused then full backend suite (last: 630 passed) | Suite green |
| 1.2 | Review SQL/security/performance advisors for the notification-recovery migration; decide on an index; reconcile migration history | Advisor output, migration list |
| 1.3 | Apply migration and release backend together; watch CI and the exact Vercel deployment | CI + READY deployment |
| 1.4 | Controlled production crash-recovery and owner-alert acceptance (uncertain sends must not replay; unresolved goes to operator review) | SQL receipts, one alert email |
| 1.5 | Ship the availability-monitor retry patch (bounded retries, per-attempt diagnostics) | Monitor run summary |
| 1.6 | Set a strong `CRON_SECRET` in production; deploy; run worker and scheduled-SMS acceptance in restricted mode | Worker run log, one scheduled SMS to the allowed number |

## 5. Phase 2 — Attribution and conversion (A16 remainder)

| # | Task | Acceptance evidence |
|---|---|---|
| 2.1 | Persist first-touch UTMs across navigation on Hilltop and Jays without overwriting with static campaign values | Submission shows original UTMs after multi-page visit |
| 2.2 | Mount the Meta Pixel on Hilltop (currently not mounted; utility existence is not installation) | Pixel Helper / network evidence |
| 2.3 | Fire exactly one Lead conversion per matching processed receipt; no event on validation failure; dedup keys; no PII in events | Event log: one event per receipt, zero on failure |
| 2.4 | Reports reflect source → lead → analysis → contract chain, excluding QA | Dashboard/Reports screenshot |

## 6. Phase 3 — Human and provider acceptance (owner actions)

Bundle these into one sitting; each needs a physical device, mailbox or login.

| # | Action | Why | Evidence |
|---|---|---|---|
| 3.1 | Reply STOP from the 0100 handset; confirm SMS refusal afterward | Proves opt-out end to end | Inbound event + refused send |
| 3.2 | Click the unsubscribe link in a message to a secondary authorized mailbox; confirm later send is refused (not the primary alert mailbox) | Proves email suppression | Unsubscribe event + refusal |
| 3.3 | Meta: submit a fresh test on the new consent-box native form; retire the old v1 form; approve exact deletion of dummy leads | Consent mapping is correct | Lead with consent flags; v1 closed |
| 3.4 | Confirm inbox receipt of the four Jays QA owner emails | Provider-accepted is not inbox-delivered | Owner confirmation |
| 3.5 | Restore rehearsal in an isolated project: database, Auth, Storage, Edge | Backups unproven until restored | Restore log, row-count comparison |
| 3.6 | Independent failure-alert receipt (monitor failure reaches a human outside the app) | Alerts are unproven until received | Received message |
| 3.7 | Classify the ambiguous "Julio D / 5200 Tuskegee Trail" inquiry and review the legacy unlinked "July" receipt | Reporting integrity | Classification recorded |

## 7. Phase 4 — Business decisions (unanswered since October 8; do not re-ask piecemeal)

Single decision sheet for the owner:
1. Title partner (name, contact, SOP).
2. Offer authority (who approves, max % of ARV/MAO, written rule).
3. Ad spend cap (daily and total) before any paid campaign.
4. After-hours coverage (who answers, SLA, what the system does overnight).
5. Qualified buyer roster (seed list and buyer-qualification rule).
6. Legal templates (purchase agreement, assignment, disclosures) reviewed by counsel.
7. Earnest-money process (who holds, where, refund terms).
8. Staffing for the rehearsal.

## 8. Phase 5 — Rehearsal and go/no-go

1. Staffed end-to-end rehearsal with clearly labeled fixtures: website/Meta inquiry → lead → task → owner alert → operator follow-up → analysis → pipeline → deadline tasks → reporting. Record timings.
2. Final audit: every acceptance row above has current evidence.
3. Go/no-go using section 9. Only then remove recipient restrictions (`EMAIL_ALLOWED_RECIPIENTS`, `SMS_ALLOWED_RECIPIENTS`) and enable campaigns in stages: email first, SMS second, paid ads last.
4. No launch certification while any required gate is open.

## 9. Go/no-go checklist (v1)

- [ ] Default branch equals live code; deployment guard removed deliberately
- [ ] Notification-recovery migration and backend released and accepted
- [ ] `CRON_SECRET` set; worker and scheduled SMS accepted
- [ ] STOP and unsubscribe refusals proven
- [ ] Meta v1 form retired; consent mapping proven
- [ ] First-touch attribution and single conversion proven
- [ ] Restore rehearsal passed; independent alert receipt confirmed
- [ ] Title partner, offer authority, ad cap, after-hours coverage, buyer roster, legal templates, earnest-money process decided
- [ ] Staffed rehearsal completed with timings
- [ ] Calling and nurture confirmed disabled (v1.1)

## 10. Deferred to v1.1 and the roadmap

- Retell: account, KYC/identity, agent and script, voice cutover, controlled call + signed callback + handback, script versioning.
- Nurture sequences.
- README roadmap: CSV export, HOT-lead email, calendar sync, strategy preference in profile, deal comparison, buyer auto-matching, audit-log UI, import deduplication, webhook integration tests, dark mode.
- Lint debt: 149 baseline findings, gated against regression, burn down opportunistically.
- Collector PR #20 still has a stale frontend test for a removed button; do not treat it as ready.

## 11. Safe-operation rules

- No real seller contact during verification; fixtures are labeled and reversibly excluded from reporting.
- Calling and nurture stay disabled; recipient restrictions stay until the final audit.
- No paid ads before the ad cap is set.
- Re-verify live state before acting; the evidence files record October state.
