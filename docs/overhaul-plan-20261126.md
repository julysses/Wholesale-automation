# WholesaleOS overhaul plan — run live while rebuilding (November 26, 2026)

Status: **PLAN ONLY. No item is approved for implementation yet.** The owner asked for the list first; each batch needs explicit go-ahead. Companion docs: `docs/business-review-20261126.md` (why), `docs/code-review-20261126.md` (technical findings), `tasks/HANDOFF-NEXT-AGENT.md` (current state and rules).

The [seller-inquiry milestone](seller-inquiry-milestone.md) is the operating plan and current baseline. A verified seller decision and outcome is the first measure of progress. The six batches below describe how to support it. Use the first 30 days to operate the live workflow and identify the highest-cost failure points. Schedule wider feature delivery after that review or explicit reprioritization.

## Owner constraints (2026-11-26)
- Facebook ads are running. The current model must keep working throughout.
- A complete overhaul is likely, built in the background.
- No changes until the owner approves; owner asked Claude to choose the batch order (below).

## Operating rules during the overhaul
1. **Live line**: the last deployment comparison matched the application code at `77e257f`. Reconfirm the live SHA before branching. Hotfixes only; every deploy tagged with its commit.
2. **Overhaul line**: one new trunk, preview deploys, isolated staging database with synthetic or masked fixtures and outbound providers disabled. Only a separately approved release moves to production.
3. **Expand-only schema** while old and new code coexist: add tables/columns; no renames or drops until cutover is complete.
4. **Feature flags per screen/flow**: run old and new in parallel, compare, switch, keep rollback.
5. **Intake (Facebook, website forms, owner alerts) migrates last**, after a shadow run reconciles each source receipt, CRM lead, task and intended owner alert. Compare retry and failure handling, missing records and duplicates. Keep one live sender and a tested rollback for 2 weeks.
6. Heavy proof gates only for consent, money, contracts and migrations; lightweight review for UI.

## Change list

### A. Protect the live model (low risk)
| # | Change | Description |
|---|---|---|
| A1 | Hotfix branch and deploy tagging | Branch from live `77e257f`; record the commit on every Vercel deploy. |
| A2 | Finish Facebook attribution | Register campaign/ad mappings (needs Ads Manager IDs), apply `20261126000000_facebook_attribution_reconciliation.sql`, deploy wiring, backfill the 7 existing leads. |
| A3 | Intake health monitor | Daily read-only check: Facebook/web leads arrived, task created, owner alerted; flag a zero-lead day for investigation. Distinguish quiet demand from missing receipts, tasks or alerts. |
| A4 | Overdue task triage | Refresh the backlog, then review seller promises first. Record reasons when resolving stale or duplicate work and assign an owner and due time to live items. Use the dated operating baseline. |

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
| C1 | Scorecard home screen | Weekly view: source → human response → decision → offer → contract → exit, with appointment counts, overdue promises, source spend, operator time and realized contribution by exit. |
| C2 | Unified lead inbox with SLA timers | One operator inbox with separate views for seller inquiries and sourced prospects. Show primary, backup, next action, raw and staffed clocks; target 5 staffed minutes and escalate at 15. |
| C3 | Multi-exit underwriting | Evaluate Hilltop purchase, resale, hold and feasible build-to-rent/duplex/quad first; compare assignment as fallback. Keep any other structure as a separately reviewed exception. Show sourced assumptions, downside and capital required. |
| C4 | Offer workflow | Offer from analysis → approval under offer-authority rules → sent/countered/accepted/expired. |
| C5 | Contract and title handoff | Separate principal and assignment closings. Require title handoff, earnest money, signed evidence and deadlines for the selected exit. A principal closing must work without an assignee or assignment agreement. |
| C6 | Buyer CRM and disposition | Buyer intake, buy box, proof of funds, tiers; automatic deal-to-buyer matching; consented deal announcements; assignment tracking. |
| C7 | Outcome attribution | Carry verified source/campaign/ad to an evidenced pass, offer, contract and applicable exit. Separate assignment fees, realized resale contribution, and held-property cash flow. |

### D. Channels (activate only on proven conversion)
| # | Change | Timing |
|---|---|---|
| D1 | County distress pipeline strengthening (Collin/Dallas) | Early |
| D2 | Consent-checked follow-up sequences | After C2 |
| D3 | AI voice | Deferred under the current human-response plan. Any reconsideration requires a separate owner decision. |
| D4 | Direct mail (manual pilot first) | After manual pilot |
| D5 | Virtual caller / agency calling | Deferred |

## Recommended batch order (owner delegated the choice)

| Batch | Items | Why first | Live impact |
|---|---|---|---|
| **1 — Protect and see** | A1, A3, A4, then A2 (when IDs available) | protects the ad spend now running and triages the operating backlog | Process/read-only/additive |
| **2 — Isolate the rebuild** | B1, B2 | Every later change needs one trunk and a staging environment | None |
| **3 — Visibility and speed** | C1, C2 (parallel to old screens, flag switch) | Speed-to-lead and a scorecard drive conversion immediately | Flagged; old screens remain |
| **4 — Money path** | C3, C6, then C4 | Underwriting plus buyers create revenue; offer workflow follows | Flagged |
| **5 — Close the loop** | C5, C7, B3–B6, D1, D2 | Cleanup and attribution once core path works | Flagged / cleanup |
| **6 — Migrate intake, then scale channels** | Intake cutover (parallel run, matched counts, 2-week fallback); D4 pilot expansion only if economics support it; D3 deferred | Highest-risk move goes last | Controlled cutover |

Original engineering estimates were weeks 1–2 for batches 1–2, weeks 3–6 for batch 3, weeks 6–10 for batch 4 and weeks 10–12 for batch 5. Reforecast at the first 30-day operating review using staffing, approvals, verified bottlenecks and intake parity. B7 applies across batches.

## Owner decisions needed (blocking specific items)
1. Who owns the daily lead queue (owner or hire) → C2 escalation design.
2. Offer authority (max % of ARV, approver) → C4.
3. Build-to-rent/duplex assumptions (cap rate, cost per sq ft, target returns) → C3.
4. Title partner and earnest-money process → C5.
5. Ads Manager campaign/ad IDs (or attached computer) → A2.
