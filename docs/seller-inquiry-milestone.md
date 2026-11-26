# Hilltop’s next milestone: one qualified seller inquiry through decision and outcome

Julio adopted this operating milestone on November 25, 2026 (Mountain time). Use it to prioritize work and judge progress. The [overhaul plan](overhaul-plan-20261126.md) remains the engineering backlog with its existing approvals. A shipped feature, a test submission, or a dashboard update does not complete this milestone.

## Current checkpoint

| Item | State |
|---|---|
| Milestone | Open. The plan is recorded. No qualifying case has been verified for this checkpoint. |
| Next action | In the private CRM, review genuine inbound inquiries in receipt order. Check whether one already has a qualifying property, a timestamped human response and an underwriting decision. Start with existing evidence so no seller receives duplicate contact. If none qualifies, use the next genuine qualifying inquiry. |
| Evidence location | Lead activity, tasks and analysis in the private CRM. Keep seller details, record IDs, communications, documents and case links there. Use this public file for stages, aggregate counts, blockers and the next action. |
| Human ownership | Identify the assigned acquisitions operator and staffed hours in the private queue. A human owns seller communication and offer approval. No AI calls. |
| Engineering | Use the existing workflow first. Record specific friction against the affected stage. The separate overhaul approval process still applies. |

## What counts as the first completed case

| Stage | Evidence the operator should be able to recover |
|---|---|
| Qualify | Genuine seller or authorized representative, identifiable property in Dallas or Collin County, verified off-market status, and interest in discussing a sale. Record source, receipt time and verification basis. Keep QA, duplicates, listed properties, out-of-area leads and unanswered county prospects in their proper categories. Unknown qualification stays pending. |
| Respond | Record the first actual human reply, channel and timestamp, plus any promised follow-up. Use the seller’s permitted channel. Aim for a human reply in 5 staffed minutes. Escalate to the designated backup at 15 staffed minutes. Keep 15 minutes as the first-case acceptance window and propose a weekly floor of 90% within it. For after-hours arrivals the staffed clock starts at the next opening. Record raw elapsed time as well. An automated acknowledgment is a separate event. A late reply remains visible in the cohort while the first on-time case is still outstanding. |
| Decide | Evaluate a Hilltop principal purchase first. Record a defensible value range, repairs or site costs, carry and selling costs where applicable, required return, maximum price and downside. Cite comps, bids or other evidence privately. A decisive fact can support an early pass. Record that fact and its source. Put unresolved material questions on a dated task. Consider assignment only when a credible buyer price and costs support it. |
| Record the outcome | Save who made the buy-or-pass decision, when, why, and what actually happened. A documented pass with the seller follow-up resolved can complete the milestone. For a buy decision, record the actual offer status and any promised update, owner and due date. An approved offer awaiting delivery is still pending. Track later acceptance, loss, principal closing or assignment as separate events. |
| Verify | Reopen the private case and trace source → human response → decision → actual outcome. Verify timestamps, evidence, owner and open obligations. Record the verification date and aggregate milestone status here. A principal purchase must be recorded truthfully even if the current CRM requires an assignment document to mark it closed. Track that limitation and use a private closing record until the workflow supports it. |

## Repeat until cost, time and margin are known by source

Use **the next ten consecutive qualified inquiries** as a proposed first review cohort. Keep misses, passes and pending cases in the cohort. Review weekly, show sample sizes, and continue beyond ten for sources with immature outcomes. Record each property inquiry once and distinguish the original source from a campaign or ad that remains unknown.

| Weekly measure | Calculation and interpretation |
|---|---|
| Volume and conversion | Show genuine inquiries, qualified inquiries, timely replies, decisions, offers sent, contracts and realized exits by source. Report disqualification and pass reasons separately. |
| Time and effort | Track raw and staffed response minutes, receipt-to-decision time and observed operator minutes per qualified inquiry. Report the median and missed promises with the count observed. Mark unlogged time unknown. |
| Acquisition cost | For a consistent period or acquisition cohort, divide attributable source spend by qualified inquiries, then by attributable contracts. State the spend window and allocation method. Keep unattributable spend visible. A zero denominator is unavailable. |
| Contribution and margin | For a resale, deduct purchase basis, improvements, financing, holding and selling costs from actual proceeds. For an assignment, use fees collected less direct deal costs. At source level deduct attributable marketing once, including spend on cases that passed. State whether labor is included. For a hold, report invested cash and actual cash flow separately. Show forecasts, open deals and unknown costs explicitly. |
| Decision to scale | Compare like exits and mature cohorts. Report realized dollars and the revenue denominator if quoting margin percentages. Where a source has no realized exit or material costs are unknown, report the gap and continue collecting evidence. |

## Production baseline • November 25, 2026 (Mountain)

One read-only production SELECT returned only counts. Lead intake uses a rolling 60-day window. Other figures below are current or lifetime counts as labeled.

| Measure | Verified count |
|---|---:|
| Lead records created in 60 days / included by the CRM reporting view | 171 / 145 |
| Total / reportable deal analyses | 2 / 0 |
| Total / reportable deals | 1 / 0 |
| Reportable leads currently in the offer-made stage | 0 |
| Buyers on file | 0 |
| Open tasks / overdue / overdue by more than 30 days | 184 / 183 / 122 |
| Tasks currently marked completed | 19 |
| Facebook-source records / reportable / reportable with an ad creative linked | 9 / 7 / 0 |
| Native Facebook submission receipts | 7 |

Reportable means included under the CRM's exclusion rules. Qualification, seller intent and off-market status require case evidence. The earlier [business review](business-review-20261126.md) identified 77 Collin pre-foreclosure prospects. That historical cohort needs a separate eligibility review. The query did not verify case histories or activity outside the CRM. The first-case milestone remains open.

## First 90 days of operations

| Window | Operating work | What to review |
|---|---|---|
| Days 1–30 | Spend 15 minutes each staffed day on new inquiries, seller promises due and unowned follow-ups. Assign a primary and backup. Triage overdue work by source and age, starting with commitments to sellers. Resolve completed or duplicate items with a reason, reassign live work and date the next action. Refresh counts before any cleanup. Classify county prospects separately by current filing, geography, listing status and permissible contact channel. | First verified case, then ten consecutive qualified inquiries. Track ten evidence-backed analyses, five economically supportable offers and 25 qualified local buyers as planning targets. Report actuals and shortfalls. A justified pass counts as a decision and never needs a token offer. Verify buyers by geography, property type, budget, funding evidence and ability to close. |
| Days 31–60 | Review the scorecard weekly using available records. Use operating evidence to prioritize a scorecard home screen, a staffed inbox with escalation and side-by-side economics for buy/rehab/resell, hold, infill development or assignment. For a viable development exit, record zoning, utilities, build and finance costs, sensitivity and required return. Route only feasible cases into Hilltop’s principal pipeline. | Compare the 5- and 15-minute response rates, seller promises kept, appointments, offers, contracts, operator effort and backlog age by source. Link the approved offer to actual delivery, counter, acceptance, expiry or loss. Track title, earnest money and deadlines for a contract. |
| Days 61–90 | Review each source monthly for acquisition cost, conversion, cash payback, realized contribution and operator time. Pick one bounded expansion only when the cohort is mature enough and seller follow-up remains dependable. A direct-mail trial uses one vendor, one list, a budget and a stop condition before batch automation. | Compare cost per contract with cash actually recovered and time to recovery. Leave payback pending for an immature cohort. Keep virtual callers, agency calling and AI voice deferred. Revisit expansion to another metro or a software product only after repeatable DFW profitability. |

For the first 30 days, prioritize operating the existing workflow. Focus engineering proposals on live intake reliability, security fixes and evidence-backed Facebook attribution. The [six engineering batches](overhaul-plan-20261126.md) retain their order and approvals. The operating windows are review points, independent of software delivery dates.

## Handoff after each session

Update the current checkpoint and append a dated row below. Record the stage reached, what was verified, what remains unknown and the single next action with its owner. Reconcile against private CRM history before acting. The operating milestone is separate from authorization to contact a seller, change ads, apply migrations or deploy.

| Date (Mountain) | Verified progress | Next action and owner |
|---|---|---|
| 2026-11-25 | Julio adopted the milestone. Codex recorded the plan. Case evidence has not yet been reviewed against these criteria. | Acquisitions operator: inspect the existing private queue for the first eligible case and its recorded human response. |
| 2026-11-25 | Compared operating and overhaul plans. One aggregate production read refreshed the baseline. First-case verification remains open. | Acquisitions operator: inspect the earliest eligible private CRM inquiry and verify its human-response history. |
