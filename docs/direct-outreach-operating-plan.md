# Dallas / Collin sourcing and direct outreach

Updated October 13, 2026. Owner objective: source our own opportunities and develop lawful direct marketing, including SMS. This is the implementation plan, not clearance to cold-text a purchased or skip-traced list. Launch remains NO-GO while acceptance gates are open.

## Operating flow

1. Collect each approved county/source separately with a filing-date window, stable document IDs, all pages, provenance and reviewed coverage ledger. Retain partial/blocked status. A tax-roll entry alone does not establish current delinquency; verify assessment year, balance/status and source refresh date. A foreclosure notice alone does not prove an active sale or current ownership.
2. Normalize parcel/address and owner identity. Compare across all source types and the entire CRM; attach another distress event to an existing property rather than create another seller or tracing job. Quarantine uncertain matches. A newly downloaded row is not necessarily a new opportunity.
3. Trace only verified new, eligible opportunities lacking usable contacts and prior completed/unresolved trace history. Recheck current owner and provider quote immediately before submitting. Use PropStream UI only. Reserve against both daily budget and the owner's $50 TOTAL authorization; unknown provider outcomes retain the full hold. Reconcile receipt, cost and returned contacts before another order. Never reload or use card fallback.
4. Place discovered contacts in an acquisition pool with SMS permission unknown. Do not start a text sequence from ingestion, review approval, DNC screening, a phone match, or a tracing receipt.
5. For owners without documented permission, prepare a personalized mailed invitation with the company's identity and an owned website/QR link or inbound contact option. Mail production/postage and any paid advertising need a separately defined budget. This plan creates drafts, not mail orders. Do not disclose foreclosure/tax distress on the envelope or in a message to an unverified recipient.
6. On the owned seller form, offer a separate optional, unchecked SMS permission choice. Preserve the exact displayed disclosure, version, timestamp, phone, sender/brand, subject, source page and affirmative action as an immutable receipt. Form submission must still work without SMS permission. Verify brand matches the registered sender. Existing website consent handling must be reused and tested before creating another receipt format.
7. An owner-initiated text can receive a relevant conversational response. Do not turn that conversation into recurring marketing without the required additional permission and accepted receipt integration.
8. Before every queued send, verify matching current permission, ownership/contact association, provider campaign/use case, suppression/STOP status, applicable DNC eligibility, permitted local time and frequency. Use conservative business hours (proposed 9am–6pm recipient local time; hold unknown timezone), identify the sender, support STOP/HELP, and reconcile the durable send/delivery receipt. A2P registration is not permission to contact a person.
9. Pause follow-ups on reply for human handling; immediately suppress wrong-party, not-interested and opt-out responses across acquisition campaigns. STOP must win over queued retries and later imports. Re-opt-in requires new valid evidence; never clear suppression from a new list import.

## Current legal/provider boundary

Twilio requires prior consent for messages on its service, written consent for promotional messaging, sender/subject-specific evidence, and straightforward opt-out. An inbound conversation does not authorize recurring outreach. Manual clicking, low volume, or rotating numbers does not remove these provider requirements. Source: [Twilio Messaging Policy](https://www.twilio.com/en-us/legal/messaging-policy), checked October 13, 2026.

Texas's current Secretary of State FAQ says prior-consent texts do not require the Chapter 302 registration statement under the described litigation position/agreement. It also says the agency does not decide an individual business's registration obligation. Do not assume every real-estate purchase inquiry is covered, exempt, or needs a $10,000 bond. Source: [Texas SOS registration FAQ](https://www.sos.state.tx.us/statdoc/faqs3400.shtml), checked October 13, 2026.

Before adopting a cold-contact texting route, obtain a Texas telecommunications attorney's written application of federal TCPA/FCC rules, Texas Chapters 302/304/305 and relevant exemptions to our exact purchase/assignment model, message copy, dialing method, recipient locations and consent evidence; separately obtain the proposed provider's written acceptance of the actual use case. Do not represent a campaign as opted-in if it is not. Other wholesalers' practices are not evidence of our eligibility. No attorney or vendor has been contacted by this work.

## Acceptance checklist and implementation status

- [x] Existing trace reservation, replay and contact receipt workflow reviewed; existing enrichment blocks repeat tracing.
- [x] Added cumulative $50 SQL cap and operator display on the launch branch; local tests cover historical spending, uncertainty, replay, unused reservation release and legacy over-cap dispatch.
- [x] Applied only the new migration to rehearsal as `20261013165414_list_trace_total_cap` (local version `20261013164454`). SQL verified $50 cap, $0 committed, no configured daily budgets, all sources disabled, service-role access allowed and browser-role access denied. Production untouched.
- [ ] Reconcile provider balance and any externally placed orders: database cap only covers recorded requests and cannot detect off-platform spend.
- [ ] Complete stable two-pass Dallas/Collin foreclosure collection and notice review; prove five clean supervised runs per county.
- [ ] Implement/verify tax-delinquency collectors against authoritative current delinquency data. Generic tax pages are discovery links, not accepted feeds. Probate/code sources each need their own acceptance.
- [ ] Deploy and verify source-scoped rehearsal ingress. Latest rehearsal Edge-function inventory was empty; sources remain disabled.
- [ ] Prove dedupe and only-new selection end to end, including one property present in multiple source lists, owner changes and ambiguous matches.
- [ ] Verify PropStream quote/order/CRM receipt recovery without duplicate spending.
- [ ] Finalize sender/legal entity, actual campaign copy and optional consent disclosure with qualified review; verify registered provider campaign matches.
- [ ] End-to-end controlled opt-in, no-consent, wrong-number, STOP, queued-send race, retry and re-opt-in acceptance. No actual owner texts during QA.
- [ ] Enable the saved collection schedule only after ingestion, worker alerts, digest and release gates pass; then observe 14 unattended days. The scheduler definition alone is not an operating collector.

## Draft outreach material (not published or sent)

Mail invitation: “Hi [owner], I'm Julio with [verified business name]. If you would consider selling [property address], you can request a no-obligation conversation at [owned seller-form URL]. You're welcome to contact us when it suits you.” Avoid foreclosure urgency, government affiliation or guaranteed-outcome claims.

Optional form disclosure for legal/provider review: “I agree to receive texts from [registered business name] at the number provided about my property inquiry and purchase discussions, including automated messages. Consent is optional and is not a condition of an offer or purchase. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. [Terms] [Privacy].” These placeholders must resolve before publication.

First SMS, only after matching consent: “Hi [first name], this is Julio with [registered business name], following up on your property inquiry. Is now a good time to discuss [property]? Reply STOP to unsubscribe.” Current sender use case must permit this exact message flow; do not send this to someone who never inquired.
