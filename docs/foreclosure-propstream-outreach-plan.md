# Foreclosure priority list → PropStream → outreach → follow-up

Owner requirement confirmed October 13, 2026: manage the complete workflow inside WholesaleOS. New Dallas and Collin foreclosure notices are daily high-priority review items. After property/owner verification, trace only eligible new opportunities through PropStream, save matched contacts to the CRM, evaluate channel readiness and track every next action.

## Required app stages

| Stage | Entry evidence | Next action |
| --- | --- | --- |
| High priority — new notice | First receipt of a distinct county/notice identity, Central date | Review all notice pages, property identity, filing and current sale status |
| Ready for skip trace | Verified property and owner, actionable foreclosure status, no reusable contact and no prior completed or uncertain trace for the same opportunity | Build the PropStream batch and verify its exact quote |
| Tracing in progress | Reserved budget and saved request identity; provider submission recorded | Reconcile the original PropStream order; never blindly retry |
| Contact found | Provider result matched to the exact CRM lead/property; contact details, provider receipt, timestamp and actual charge saved | Check contact accuracy, channel eligibility and suppression status |
| Ready for outreach | At least one specific channel passes the application's current eligibility checks | Queue that channel; recheck eligibility at dispatch |
| Follow-up due | Attempt/response recorded with owner and next-action date | Highlight due and overdue actions in WholesaleOS |
| Needs review / suppressed | Uncertain identity, missing result, wrong number, no eligible channel, opt-out or other block | Show the reason and responsible next action; no automatic send |

These are required workflow states, not a claim that every stage is implemented or active. A skip-trace result supplies contact data; it does not create documented SMS consent. Eligibility must be per channel and recipient, not a generic contact-ready checkbox. Opt-outs and wrong-party results must remove the affected destination from pending outreach. Other channels require their own approved operational rules; no alternate-channel authorization is inferred here.

## PropStream handoff

- Use the signed-in PropStream UI as previously directed. Do not invent an API integration or extract browser credentials.
- Batch only verified eligible opportunities. The currently displayed 654 foreclosure notices are evidence-review items, not a ready-to-purchase trace batch.
- Match every provider row to the saved CRM lead/property and trace request; preserve owner/property input and its hash.
- Reuse usable existing contacts. Never trace a repeated county observation as a new lead. Hold submitted or uncertain orders until provider reconciliation.
- Existing authorization remains $50 prepaid TOTAL across all days and orders. Verify the live balance and exact quote; no replenishment, card fallback or recurring purchase. The cap does not authorize tracing every imported notice.
- Save returned contacts, no-match outcomes, provider order receipt and confirmed spend. An empty result must not silently restart paid tracing.
- All queue status, budget holds, returned contacts, readiness reasons and follow-up ownership must be visible inside WholesaleOS. PropStream is the external enrichment step.

## Implementation and acceptance checkpoint

- [x] Daily high-priority notice inbox and dashboard link deployed to rehearsal; 490 Dallas +164 Collin unique notices.
- [x] Durable notice first-seen identity prevents repeat imports from appearing new.
- [x] Existing tracing services support immutable input, reservation/claim/settlement, contacts and uncertain-outcome holds, with cumulative budget enforcement.
- [ ] Verify real foreclosure property/owner/current-status evidence and create the eligible CRM associations. One real Collin property/owner association is verified; its signal remains inactive pending current trustee cancellation/postponement verification. Remaining unresolved unique notices: 490 Dallas + 163 Collin. The synthetic fixture is excluded.
- [x] Implement per-lead verified-candidate quote/reservation/start/result controls, linked follow-up tasks and uncertain-action recovery. Rehearsal migration applied and read-only handoff/budget UI verified; real purchase/result acceptance remains pending.
- [ ] Extend accepted per-lead handoffs to a verified multi-lead provider batch with exact per-lead receipt/cost mapping.
- [ ] Demonstrate one authorized eligible PropStream order and exact result/charge reconciliation without retracing on refresh or lost acknowledgement.
- [ ] Surface Contact Found and per-channel Ready for Outreach states with recorded eligibility reasons.
- [ ] Complete controlled delivery, STOP/suppression, response and follow-up acceptance before enabling real outreach.
- [ ] Activate daily collection only after collection/monitoring readiness gates; production release remains separately gated.

No PropStream order, spend, seller message, schedule activation or production promotion was performed while recording this requirement. Resume with the real identity-verification gate, then candidate selection and provider reconciliation. Do not mark the pipeline complete from the existence of this plan.
