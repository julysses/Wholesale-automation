# WholesaleOS business and process review — November 26, 2026

Read-only, aggregate production data (no personal data), Supabase project `dvzhzlipbwzzcliujzyz`, queried today.

## 1. Verdict

The platform is strong on engineering and compliance, but the business isn't converting. The constraint today is **operating (follow-up, offers, buyers)**, not software. More features will not close the gap. WholesaleOS can help Hilltop beat much larger operators on **speed, local data, exit flexibility and cost per deal**. It cannot beat them on ad spend or brand, so the product should be narrowed to those four advantages.

## 2. What the numbers say

| Metric | Value | Reading |
|---|---|---|
| Leads in database | 17,503 | Mostly imported lists. Volume isn't the problem |
| New leads, last 60 days | 171 (83 web form, 24 of them excluded as QA/spam; 77 Collin pre-foreclosure; 9 Facebook; 2 Dallas county) | ~145 real inbound/outbound-ready leads in 60 days. Enough to produce deals |
| Deal analyses | 2 (both QA) | **No real property has been underwritten in the system** |
| Deals | 1 (cancelled QA) | **No offers or contracts recorded** |
| Buyers | 0 | **No disposition capacity.** A wholesaler with no buyer list has no exit |
| Open tasks | 186, of which 185 are overdue (179 >7 days, 124 >30 days) | Follow-up isn't happening, or isn't being recorded |
| Tasks ever completed | 19 | The task system isn't the operating rhythm yet |
| Facebook leads attributed to an ad | 0 of 9 | Ad spend can't yet be tied to outcomes |

Engineering output over the same period is several hundred commits, 1,187 backend tests, extensive evidence files and gated releases. The ratio between engineering effort and closed business is inverted.

## 3. Why this happened (process diagnosis)

1. **The build became the job.** Agent-driven development (Codex/Claude) optimizes for correctness gates, evidence and edge cases. Each feature carries rollback proofs and acceptance matrices. That suits consent, money and legal paths, but it was applied to everything. Velocity went into infrastructure while lead handling stayed manual and unworked.
2. **No operating cadence is wired to the app.** Tasks are created for every inquiry, but nothing forces them to be worked: no daily queue SLA, no escalation, no scorecard.
3. **The value chain is built back to front.** Intake, scoring, consent and recovery are deep. Underwriting, offers, contracts and buyers are thin or empty in production. Revenue is created at offer, contract and assignment, which is the least-used part of the system.
4. **Scope keeps widening.** Facebook, website(s), county ingestion, PropStream, Retell SMS, inbound AI, direct mail, virtual callers, an agency pilot, development command center and land are all in flight across ~30 branches. Each one is half-activated.

## 4. How large operators win, and where Hilltop can

| Large-operator model | Their edge | Where you can't match | Where you can beat them |
|---|---|---|---|
| National cash buyers / franchises (e.g. "We Buy Houses"-style brands) | Brand, PPC/TV budget, call centers | Ad spend and name recognition | **Speed and personal follow-up**: an owner-operator answering in minutes vs a call-center script |
| National wholesalers with large buyer networks | Disposition machine, many buyers per market | Buyer volume nationally | **Local DFW buyer depth plus being a buyer yourself** (build-to-rent, duplex/quad, owner-builder). You can close deals others must pass on |
| iBuyers / tech platforms | Algorithmic pricing, capital | Balance sheet, data science teams | **Distressed and complex properties** they avoid; underwriting judgment from M&A discipline |
| Off-the-shelf investor CRMs (REsimpli, InvestorFuse, BatchLeads, Carrot and similar) | Cheap, mature, covers ~80% of CRM, dialer, list-stacking and websites | Feature breadth per dollar | Custom pieces they can't sell you: **county distress feeds, your scoring, multi-exit underwriting including your own development exits, your outcome data loop** |

The point of the comparison: the "largest models" win on capital. A one-market operator wins on **speed-to-lead, local proprietary data, more exit strategies per lead and lower cost per contract**. The app should exist to maximize those four and nothing else.

## 5. What makes WholesaleOS a real moat (keep and deepen)

1. **Proprietary distress data**: Collin/Dallas pre-foreclosure, tax-delinquent and foreclosure ingestion with scoring. Competitors buy the same PropStream lists; county-first data is earlier and differentiated.
2. **Multi-exit underwriting engine**: one analysis computes wholesale assignment, wholetail, novation and **your own build-to-rent/duplex development** return. This is a rare advantage: you can be the end buyer.
3. **Speed-to-lead automation**: instant owner alert plus seller acknowledgment, with consent already engineered. This is the highest-ROI piece already built.
4. **Outcome data loop**: source → contact → appointment → offer → contract → assignment fee, by channel and campaign. Over time this tells you exactly where each dollar of marketing returns, which competitors with generic CRMs rarely achieve.
5. **Compliance-by-design**: consent evidence, suppression and immutable receipts. This is an asset (TCPA exposure is a real risk at scale), but it should be a foundation rather than the product.

## 6. What to stop, defer or buy instead of build

| Area | Recommendation | Why |
|---|---|---|
| Virtual caller, agency calling pilot (gates 4–5) | **Defer** | No conversion proof yet; adds legal and ops load |
| Inbound AI voice agent | **Defer until** follow-up SLA holds for 30 days | AI on top of an unworked queue just adds volume |
| Direct mail automation | **Run manually first** (one vendor, one list, one month), automate after it proves cost per contract | Avoid building fulfillment for an unproven channel |
| Legacy VAPI, Jinja UI, extra hosting configs | **Delete** | Maintenance cost, zero value |
| Generic CRM features (dialer, generic SMS blasts) | **Use a tool** if needed | Commodity |
| Evidence/gate process for every UI change | **Lighten** | Keep heavy gates only for consent, money movement, contracts and data migrations |

## 7. The operating system to install (process before code)

**Daily (15 minutes, owner or acquisitions rep):**
1. Work every new inquiry within 5 minutes during business hours and 1 hour after hours. The system already alerts you, so set the SLA and measure it.
2. Clear the "My Follow-ups" queue to zero. Today: triage the 185 overdue tasks in one sitting (close stale ones, reschedule live ones).
3. Every qualified conversation gets an analysis. Every viable analysis gets an offer within 24 hours.

**Weekly scorecard (one screen, the only dashboard that matters):**

| Stage | Weekly target to set | Unit economics to track |
|---|---|---|
| New real leads by source | baseline from last 60 days (~17/week) | cost per lead by source |
| Contacted within SLA | ≥90% | median speed-to-lead |
| Appointments / qualified conversations | set after 4 weeks | contact → appointment % |
| Offers made | set after 4 weeks | appointment → offer % |
| Contracts signed | set after 4 weeks | offer → contract %, **cost per contract** |
| Assignments / closes and fees | — | average fee, days to assign |
| Active buyers (with buy box) | 25 in 30 days, 75 in 90 | buyers per deal, days to assign |

**Monthly:** kill or double the channel with the worst/best cost per contract.

## 8. 30/60/90-day plan

**Days 1–30: operate what exists (feature freeze except fixes)**
- Triage the 185 overdue tasks; enforce the follow-up SLA.
- Work the 77 Collin pre-foreclosure leads with a call/text/mail touch sequence (consent-compliant), plus all web and Facebook leads.
- Build the buyer list to 25 qualified buyers (local REIA, title-company relationships, cash-buyer records from county deeds). Disposition capacity is the single biggest gap.
- Register Facebook campaign/ad mappings so spend ties to leads (already in progress).
- Make the first 10 real underwriting analyses and 5 real offers in the system.

**Days 31–60: tighten the money path**
- Ship the weekly scorecard as the home screen (data already exists; one view).
- Make underwriting multi-exit (wholesale, wholetail, novation, build-to-rent/duplex) with your own development math. This is the differentiator.
- Merge branches to one trunk; deploy from Git.

**Days 61–90: automate only what is proven**
- Automate the channel with the best cost per contract (likely county distress plus follow-up sequences, or Facebook if attribution shows it).
- Only then consider inbound AI for after-hours coverage and direct-mail batches.

## 9. Would this help you compete?

Yes, conditionally. The software is already more rigorous than what most small and mid-size wholesalers run. The edge comes from using it to **respond faster, underwrite better and own more exits** than national players in DFW, and from measuring cost per contract by channel. It does not come from out-building their feature sets. Until the system records real offers, contracts and buyers, it's an expensive intake engine. Redirect the next 30 days from building to operating, and let deal data decide what gets automated next.

## 10. Leverage opportunities specific to your profile

- **Be your own best buyer.** Route deals that fail wholesale math but pass build-to-rent/duplex math into your development pipeline. That turns dead leads into portfolio assets.
- **Apply M&A discipline.** Treat each channel like a portfolio company: CAC, conversion, payback. Kill underperformers quickly.
- **Use land and lots** (the app has land modules) as a DFW infill sourcing channel for your duplex/quadplex builds; national wholesalers rarely target it.
- **Productize later.** If the county-data plus multi-exit underwriting stack works in DFW, it's a sellable vertical SaaS or a franchise-style playbook for other Texas metros. Prove it on your own P&L first.
