# WholesaleOS overhaul plan — run live while rebuilding (November 26, 2026)

Status: **PLAN ONLY. No item is approved for implementation yet.** The owner asked for the list first; each batch needs explicit go-ahead. Companion docs: `docs/business-review-20261126.md` (why), `docs/code-review-20261126.md` (technical findings), `tasks/HANDOFF-NEXT-AGENT.md` (current state and rules).

## Owner constraints (2026-11-26)
- Facebook ads are running. The current model must keep working throughout.
- A complete overhaul is likely, built in the background.
- No changes until the owner approves; owner asked Claude to choose the batch order (below).

## Operating rules during the overhaul
1. **Live line**: production stays on the code at `77e257f` (`codex/wholesaleos-leads-workflow` = live). Hotfixes only; every deploy tagged with its commit.
2. **Overhaul line**: one new trunk, preview deploys, staging database. Never deploys to production directly.
3. **Expand-only schema** while old and new code coexist: add tables/columns; no renames or drops until cutover is complete.
4. **Feature flags per screen/flow**: run old and new in parallel, compare, switch, keep rollback.
5. **Intake (Facebook, website forms, owner alerts) migrates last**, after a parallel run with exactly matching counts, and keeps a fallback for 2 weeks.
6. Heavy proof gates only for consent, money, contracts and migrations; lightweight review for UI.

## Change list

### A. Protect the live model (low risk)
| # | Change | Description |
|---|---|---|
| A1 | Hotfix branch and deploy tagging | Branch from live `77e257f`; record the commit on every Vercel deploy. |
| A2 | Finish Facebook attribution | Register campaign/ad mappings (needs Ads Manager IDs), apply `20261126000000_facebook_attribution_reconciliation.sql`, deploy wiring, backfill the 7 existing leads. |
| A3 | Intake health monitor | Daily read-only check: Facebook/web leads arrived, task created, owner alerted; flag zero-lead days during active campaigns. |
| A4 | Overdue task triage | One-time bulk review/close/reschedule of 185 overdue tasks, filtered by source and age. |

### B. Foundation for the overhaul (background)
| # | Change | Description |
|---|---|---|
| B1 | Consolidate branches | Merge acquisition (`628fc02`) and Facebook/leads (`e88a7c6`) lines into one trunk; archive ~30 stale branches. |
| B2 | Staging environment | Vercel preview plus Supabase staging branch; no overhaul work touches live data. |
| B3 | One hosting target | Keep Vercel; retire Fly/Render/Railway/Docker/Procfile after confirming the 3 Railway services are unused. |
| B4 | Remove legacy code | VAPI, Jinja pipeline UI and dead adapters, after logs confirm no traffic. |
| B5 | Unified data model | Shared entities from the acquisition plan (workspaces, contact points, permissions, eligibility, lead sources, campaigns) for every channel. |
| B6 | Code health | Split `web/api/webhooks.py` by provider; refactor `score_lead`, `record_chat_event`, `match_buyers_to_deal` behind tests; ruff gate in CI; frontend data access via hooks. |
| B7 | Right-size release process | Heavy gates only for consent/money/contracts/migrations. |

### C. Revenue path (core of the overhaul)
| # | Change | Description |
|---|---|---|
| C1 | Scorecard home screen | Weekly view: leads by source → contacted in SLA → appointments → offers → contracts → fees; cost per contract; overdue work. |
| C2 | Unified lead inbox with SLA timers | One queue for every channel; countdown, owner, escalation when untouched past SLA. |
| C3 | Multi-exit underwriting | Wholesale, wholetail, novation and owner build-to-rent/duplex/quad returns side by side; route deals that fail wholesale but pass development math to the owner's pipeline. |
| C4 | Offer workflow | Offer from analysis → approval under offer-authority rules → sent/countered/accepted/expired. |
| C5 | Contract and title handoff | Contract status, title handoff, earnest money, inspection/closing deadlines with automatic tasks (partly exists; finish and simplify). |
| C6 | Buyer CRM and disposition | Buyer intake, buy box, proof of funds, tiers; automatic deal-to-buyer matching; consented deal announcements; assignment tracking. |
| C7 | Outcome attribution | Source/campaign/ad carried from lead to fee. |

### D. Channels (activate only on proven conversion)
| # | Change | Timing |
|---|---|---|
| D1 | County distress pipeline strengthening (Collin/Dallas) | Early |
| D2 | Consent-checked follow-up sequences | After C2 |
| D3 | Inbound AI after hours (Retell) | After SLA holds 30 days |
| D4 | Direct mail (manual pilot first) | After manual pilot |
| D5 | Virtual caller / agency calling | Deferred |

## Recommended batch order (owner delegated the choice)

| Batch | Items | Why first | Live impact |
|---|---|---|---|
| **1 — Protect and see** | A1, A3, A4, then A2 (when IDs available) | Zero-to-low risk; protects the ad spend now running; clears operating backlog | Process/read-only/additive |
| **2 — Isolate the rebuild** | B1, B2 | Every later change needs one trunk and a staging environment | None |
| **3 — Visibility and speed** | C1, C2 (parallel to old screens, flag switch) | Speed-to-lead and a scorecard drive conversion immediately | Flagged; old screens remain |
| **4 — Money path** | C3, C6, then C4 | Underwriting plus buyers create revenue; offer workflow follows | Flagged |
| **5 — Close the loop** | C5, C7, B3–B6, D1, D2 | Cleanup and attribution once core path works | Flagged / cleanup |
| **6 — Migrate intake, then scale channels** | Intake cutover (parallel run, matched counts, 2-week fallback); D3, D4 by data | Highest-risk move goes last | Controlled cutover |

Rough timing: batches 1–2 weeks 1–2; batch 3 weeks 3–6; batch 4 weeks 6–10; batch 5 weeks 10–12; batch 6 after. Estimates, not commitments.

## Owner decisions needed (blocking specific items)
1. Who owns the daily lead queue (owner or hire) → C2 escalation design.
2. Offer authority (max % of ARV, approver) → C4.
3. Build-to-rent/duplex assumptions (cap rate, cost per sq ft, target returns) → C3.
4. Title partner and earnest-money process → C5.
5. Ads Manager campaign/ad IDs (or attached computer) → A2.
