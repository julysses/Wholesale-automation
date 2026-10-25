# WholesaleOS: whole-system review, XLeads comparison and solo launch plan

Reviewed October 25, 2026 (America/Chicago).

## Decision

Keep WholesaleOS as the operating record for a tightly scoped initial launch, retain the existing PropStream arrangement for now, and stop expanding features until one complete seller journey works reliably. Evaluate XLeads as a possible replacement for data preparation and, if necessary, the operational CRM. Do not maintain two competing follow-up systems.

WholesaleOS contains substantial working software and increasingly strong recovery controls. It is not yet evidenced as an unattended, end-to-end acquisition business. The biggest constraints are incomplete live acceptance, manual source verification, misleading Facebook readiness indicators, and owner workload. XLeads offers a simpler packaged starting point, but its advertised automation and data quality have not been tested in this account or market. Neither system can establish that a distressed property owner wants to sell, or guarantee contracts.

This recommendation revisits the earlier PropStream decision because the owner explicitly requested a fresh comparison. No subscription, ads, outreach, schedule, provider setting or production database was changed during this review.

## What was actually reviewed

GitHub repository: https://github.com/julysses/Wholesale-automation

Both relevant local branches were pulled successfully, with no upstream changes to their checked-out branches:

- Release checkout: `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app`; `codex/facebook-release-candidate`, starting commit `9f04cc6ca8feb186334c6e9367f40c333db41758`.
- Separate integration checkout: sibling `integration`; `codex/wholesale-integration-review`, commit `c63f7d584a7bed74cf2cd887c6af6c04d789218d`. Two pre-existing untracked duplicate files were left alone.

Reviewed architecture, collection/provider adapters, Facebook campaign/intake flows, SMS prompt/dispatch controls, valuation logic, operator roles, and current release/integration evidence. This is a system-level source and operational-evidence review, not an exhaustive security audit or a new production acceptance test. October 23 production facts below are from the current repository's saved evidence; they were not independently re-probed today. Older October 22 integration observations must not override newer release evidence.

Current local checks: 151 focused backend tests passed; all 179 frontend tests across 42 files passed. Pipeline result is recorded in the completion section. Tests use local fixtures/mocked providers and do not prove real delivery or real seller conversion.

## Highest-priority findings

| Priority | Finding and evidence | Operational consequence | Required action |
|---|---|---|---|
| P1 | `frontend/src/components/fb-ads/steps/Step6PreFlightChecklist.tsx:41-82` hard-codes success for several settings, form/routing items, SMS sequencing and the webhook; the overall screen can display READY TO LAUNCH. | A green screen can conceal disconnected lead intake or paused follow-up. | Replace assumed checks with observed account/configuration/intake evidence; otherwise label them unverified. |
| P1 | `CampaignWizard.tsx:118-153` saves `fb_campaigns` drafts. `Step2AudienceBuilder.tsx:69-94` reads a local CSV, counts lines and stores local audience metadata; this is not a verified Meta audience upload. The separate campaign API writes `ad_campaigns`. | Drafts, audiences and running Meta ads can be confused; two internal campaign representations also need reconciliation. | Publish the pilot in Meta Ads Manager, record real campaign/ad/form IDs and verify attribution. Do not interpret local audience counts as Meta matched users. |
| P1 | `frontend/src/lib/fb-ads/battlePlanRules.ts` and the audience builder prescribe distress signals, income and lookalike tactics; the wizard blocks progression without a distress signal or uploaded audience. | The built-in playbook is not evidence those options are available or appropriate for Housing ads. | Rebuild the playbook around current permitted Ads Manager settings. Remove unsupported launch requirements and unproven highest-ROI claims. |
| P1 | Latest `docs/START-HERE-NEXT-CHAT.md` and `docs/facebook-release/LAUNCH-2026-10-23.md` record automatic SMS delivery and owner email, but actual STOP/suppression, native Meta acceptance and other gates remain open. | Successful individual messages do not establish safe unattended intake. | Complete the remaining channel-specific live checks and retain exact receipts before broad activation. |
| P1 | The October 23 checkpoint records unresolved credential-incident closure and a voice number still pointing to Twilio's demo endpoint at its last inspection. | New sellers may call an unusable number; unresolved access exposure creates operational risk. | Verify current routing and close the documented credential incident with coordinated rotation and consumer checks. |
| P2 | `tools/data_providers.py:104-132` contains PropStream and BatchLeads provider stubs that return empty lists even with keys. Separate county/PropStream handoff tooling exists. | The generic provider path is not automatic paid-list sourcing; empty results must not be mistaken for no opportunities. | Explicitly expose unsupported provider status and use the reviewed export/import handoff until a real supported integration is proven. |
| P2 | `docs/next-collection-acceptance.md` records 25 Dallas and nine Collin notices accepted into the review inventory on October 16, with no CRM lead/property/task or trace increase in that run. | Notices collected are not qualified, contactable seller leads. | Prove notice → parcel/property → current status → owner/contact → eligible channel → CRM owner/task/history, with a rejection reason at each failed step. |
| P2 | Integration release documents list 21 forward proposals unapplied at their last production check, with buyer sending, backup/restore and operator acceptance open. | Buyer/import/land enhancements cannot be advertised as deployed capability. The integration baseline also predates later release fixes. | Refresh the integration against the current release, rehearse and deploy only its reviewed forward changes; do not replay the migration directory. |
| P2 | `agents/deal_analyzer_agent.py` contains fixed repair assumptions, market price-per-square-foot fallbacks and heuristic/low-confidence valuations. | A computed offer is not proof of market value, lien balance or profitable exit. | Require comparable-sale evidence, property condition, title/payoff review and owner approval before any binding offer. |
| P2 | `frontend/src/pages/admin/Users.tsx` exposes admin/user roles. No complete manager operating model was established by this review. | Adding logins alone will not create accountable teams or market-level isolation. | Before adding managers, validate market ownership, scoped visibility, reassignment, approval limits, task escalation and reporting. |

Meta's official materials describe restricted Housing targeting, including unavailable lookalikes. The live help page required login, so the final settings must be checked in the actual account; this report does not invent a current permitted targeting menu. Sources: https://about.fb.com/news/2019/03/protecting-against-discrimination-in-ads/ and https://about.fb.com/wp-content/uploads/2022/06/June_2022_HUD_Settlement_Agreement.pdf.

## Capability assessment

- **Inbound seller intake:** strongest near-term launch path. Saved October 23 evidence links fresh Hilltop inquiries to consent receipts, assigned tasks, notifications and delivered owner email. A bounded automatic acknowledgment/reply was delivered. Native Meta and remaining website/channel acceptance still need their own proof.
- **Conversation automation:** useful for acknowledgments, short qualification, summaries and routing. The published V3 prompt deliberately does not book appointments, initiate calls, make offers or start purchased-list outreach. It is not an autonomous acquisitions closer.
- **County sourcing:** unusually valuable custom provenance, deduplication, OCR and review machinery. Its benefit depends on reducing review minutes per usable property. Current evidence supports bounded supervised collection, not a complete unattended county-to-contract service.
- **Tax/probate/code-violation lists:** adapters and scoring exist. Do not assume every category has a fresh, complete, scheduled official feed. Keep tax delinquency, recorded liens, tax-sale notices and mortgage foreclosure distinct.
- **Underwriting:** preliminary triage, with explicit source/confidence, rather than final acquisition authority.
- **Dispositions:** buyer matching/import infrastructure exists, especially in the separate candidate. The October 22 snapshot recorded an empty buyer book; refresh this before calling it an operating exit channel. Buyer SMS has its own approval and delivery gates.
- **Operations:** tasks, owner alerts, incident monitoring and durable receipt/recovery controls are meaningful strengths. A dated snapshot recorded 117 overdue tasks; classify historical/test items before deriving current workload. A solo operator needs a short prioritized queue, not hundreds of indiscriminate alerts.
- **Recovery/security:** a saved schema or successful local rehearsal is not a verified restorable business-data backup. Manager access and isolated recovery remain specific acceptance work.

## XLeads comparison

Current advertised monthly plans, checked October 25 at https://xleads.com/:

| Plan | Monthly base | Included record downloads/month | Relevant advertised distinction |
|---|---:|---:|---|
| Basic | $97 | 25,000 | CRM, skip tracing, dialer and AI-agent access |
| Pro | $199 | 40,000 | Foreclosure lists among expanded list types |
| X Plan | $249 | 60,000 | Dedicated disposition and buyer-matching features |

Published SMS rates are 2¢, 1¢ and 0.83¢ respectively; connected dialer time is listed at $1.008/hour and triple-line access at $150/month extra. These are vendor claims, not a complete quote or an independent quality assessment. Verify AI usage, carrier/registration charges, taxes, export rights and account limits before buying. Do not assume advertised access includes unlimited billable usage.

| Decision factor | WholesaleOS + existing data arrangement | XLeads alternative |
|---|---|---|
| Fastest setup from scratch | Requires technical operation and maintenance | Packaged CRM/data workflow is potentially quicker |
| Current switching cost | Existing websites, receipts, tasks and integrations retained | Migration, sender setup, permissions and acceptance must be redone |
| Distressed-property sourcing | Official county evidence with manual review burden | Convenient vendor lists; local freshness/contact quality untested |
| Automation control | Exact custom receipts, holds, routing and limits | Advertised ready-made workflows; verify exceptions and portability |
| Solo owner workload | Can be tailored tightly, but owner currently absorbs technical work | Potentially less maintenance; actual time saved must be measured |
| Later managers | Custom rules possible; access/workflow proof still needed | Demonstrate actual seats, permissions and assignment controls |
| Lead performance | No verified source-to-closed-deal cohort supplied | No verified local conversion evidence supplied |

If choosing XLeads for this brief, Pro is the relevant starting comparison because foreclosure lists are advertised there. Do not upgrade to X Plan merely for record volume. A limited vendor evaluation should use the same market, property criteria and observation period as the incumbent; compare verified owner-contact rate, stale/duplicate records, usable leads per review hour, follow-up failures and full cost. Public records are not permission to test-contact owners.

Suggested decision rule: retain WholesaleOS if the focused launch works and routine technical intervention drops below a chosen weekly time allowance. If it continues demanding daily debugging, select a managed CRM after demonstrating the complete workflow and exportability. Prior engineering spend is not a reason to keep an operating burden. Do not run both CRMs' sending automations against the same people.

## Acquisition strategy for one owner

Run two separate pipelines into one operational queue:

1. **Inbound:** one brand, one geography and one verified form path. Start with a simple seller proposition and two creative variations. Keep budget concentrated enough to evaluate meaningful conversations. Use required Housing settings, neutral copy and explicit channel consent. Capture campaign/ad/form IDs, source and timestamps. Qualify property address, ownership, condition, timing and desired outcome; review actual Meta form questions before publication.
2. **Distressed-property prospecting:** start with a small reviewed Dallas/Collin cohort. Prioritize current ownership, verified distress, likely workable equity, property fit and enough time to act. Separate urgent foreclosure deadlines from longer-cycle tax-delinquent/absentee opportunities. Add probate or other complex categories after the base workflow works. A priority score is a hypothesis, not a measured probability of conversion.

For cold lists, use a reviewed direct-mail workflow and/or compliant person-led calling after applicable DNC, state-law and provider checks. Route people who respond or opt in into the automated follow-up workflow. Do not mass-text skip-traced owners through the existing inquiry-only sender, or use AI voice as the default cold-list contact method.

Twilio requires recipient consent tied to the sender and subject and prohibits unsolicited bulk messages; an exported phone number is not consent. FCC guidance treats AI-generated voices as artificial/prerecorded voices under the TCPA, with applicable consent requirements. These requirements apply regardless of the CRM's available buttons. Sources: https://www.twilio.com/en-us/legal/messaging-policy and https://docs.fcc.gov/public/attachments/FCC-24-17A1.pdf. Obtain qualified review of the exact Texas outreach and contracting process before scale; this is not a legal clearance.

Automate intake deduplication, provenance, consent capture, owner assignment, allowed acknowledgments, reply classification, summaries, draft underwriting, task reminders and exception alerts. Keep price commitments, final comps/repairs, title/payoffs, negotiations, contract decisions, buyer selection and sensitive seller situations with you or an accountable specialist.

## Pilot economics and capacity

Use collected gross profit and owner time, not downloaded records, as the outcome. Track each source separately through unique property → verified owner → permitted contact → conversation → qualified opportunity → appointment → offer → contract → collected closing.

Illustrative planning budget only: $25/day for 30 days is $750 in ads; with an assumed $30–$75 cost per inquiry, that produces roughly 10–25 inquiries, not contracts. Those costs are assumptions, not local benchmarks, and this sample may be too small to judge closing conversion. Data, mail, phone, AI, hosting and professional costs are additional. No spending is approved by this illustration.

Calculate cost per qualified conversation, cost per kept appointment, acquisition cost per closed deal, contribution after direct costs, and owner hours per closing. Track response delay, unmatched intake, unassigned tasks, overdue seller replies, duplicates, opt-outs, delivery failures and source review time.

Illustrative capacity: 120 available operator minutes/day divided by 20 measured minutes per active opportunity gives six opportunity work units/day. Subtract negotiation, field visits and closing work before increasing marketing. Set volume from actual handling time rather than export allowances. A proposed starting service target is owner review of hot replies within 15 minutes during coverage hours, with an explicit after-hours process; validate this against your real schedule.

## Launch sequence and resumable progress

### Completed in this review

- [x] Located and pulled release and integration branches.
- [x] Distinguished shipped, candidate and historically tested capabilities.
- [x] Identified source-level readiness and provider gaps.
- [x] Refreshed XLeads pricing and relevant provider-policy sources.
- [x] Re-ran focused backend and frontend checks.
- [x] Prepared this decision record, launch sequence and progress checklist.

### Next: focused readiness sprint (proposal, not a delivery promise)

- [ ] Correct false-positive Facebook readiness and separate draft/local audience state from Meta publication.
- [ ] Verify current production release, flags, credential-incident closure and inbound voice routing.
- [ ] Complete fresh controlled STOP/suppression, reply routing and relevant email unsubscribe acceptance, preserving historical holds.
- [ ] Verify the chosen ad form → durable receipt → lead → owner/task → notification → permitted reply path. Native Meta requires an actual native submission if selected.
- [ ] Verify operator permissions, recovery/backup and a pause procedure that still preserves inbound replies and alerts.
- [ ] Reconcile the task queue, assign yourself explicitly and define coverage hours.
- [ ] Prove one fresh county batch all the way through property/owner verification and CRM follow-up, measuring manual minutes and respecting the existing cumulative $50 PropStream cap.
- [ ] Approve concrete creative, form, targeting, budget and initial channel-specific outreach before paid activation.

### Pilot and manager expansion

- [ ] Run one measured inbound campaign plus one bounded list cohort; review results weekly by source.
- [ ] Expand only after intake is reliable, every active opportunity has an owner/next action, replies meet coverage targets and economics justify more spend.
- [ ] Refresh and release broader integration separately; compare against the later production fixes first.
- [ ] Add a manager when measured follow-up/negotiation capacity becomes the constraint. Give each manager a market, queue, approval ceiling and scorecard; test cross-manager visibility and handoff before inviting a team.

Resume from this checklist and the newest section of `docs/START-HERE-NEXT-CHAT.md`. Do not follow older dated instructions that have been superseded. No application fixes are included in this review; the identified issues remain open.

## Review completion

All three current local checks passed: focused backend 151, frontend 179 across 42 files, pipeline 196. Total: 526 passing tests. Backend emitted 90 deprecation warnings; frontend emitted the expected duplicate-header parser diagnostic. No full backend suite, build, current vulnerability audit, new signed-in UI acceptance or live-provider acceptance was run in this review. These results do not close the launch gates above.

A copy of this report is tracked at `docs/WHOLESALEOS-SOLO-LAUNCH-REVIEW-2026-10-25.md` on the release-candidate branch. The separate integration checkout remains untouched by this report update.
