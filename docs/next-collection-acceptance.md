# Next bounded county collection acceptance

Prepared October 16, 2026. **User approved and completed this bounded cycle on October 16.** The earlier one-record Collin exception is complete. Production collection gates and the existing GPT heartbeat remain paused outside this exception.

## Proposed scope

One observed GPT collection cycle for Dallas and Collin foreclosure indexes, restricted to filings October 14–16, 2026. If execution occurs later, retain these explicit dates unless a new scope is agreed. No tax refresh, historical recrawl, paid document purchase, tracing order, contact export or outreach. No background Mac worker and no recurring schedule activation.

Use the current `codex/retell-sms-production` checkout and production project `dvzhzlipbwzzcliujzyz`. Older `wholesale-launch-prep/docs/foreclosure-inventory-collection.md` provides browser mechanics only; its rehearsal delivery destination is obsolete for this acceptance.

## Execution and stop conditions

1. Read the current checkpoint; verify gates, prior receipts and the shared daily claim state. Use `pipeline/collectors/scheduled_batch.py claim` before any county request. A consumed window or unavailable state stops collection; do not reset a claim.
2. In the signed-in browser, capture the official Dallas publicsearch foreclosure index and Collin ForeclosureNotices index. Verify applied filing dates and totals. Save two matching traversals, stable official IDs, visible rows, actual capture times and coverage. Stop on access restrictions, unstable totals or incomplete pages; never report incomplete capture as zero new notices.
3. Generate private manifests with the current `foreclosure_inventory.mjs` visible-source adapters. Review them locally before opening intake. Every index-only record stays partial and requires notice, property identity and current-status review. Do not create a CRM lead from an index address alone.
4. For each validated source separately, temporarily enable only its intake gate. Deliver the saved manifest through `deliver_keychain.py --environment production`; use the source-scoped Keychain credential. Preserve exact batches and delivery journals. Reclose the gate in a finally/cleanup path and verify it is off. An uncertain result is investigated from saved receipts; do not regenerate a run or start fresh delivery.
5. Check durable source/batch/record receipts and source-ID deduplication. Report new observations separately from genuinely new notices and reviewed CRM leads. Confirm outreach, trace spending and SMS scheduler are still disabled, and lead/task/contact/SMS changes are limited to expected intake bookkeeping. Preserve assigned review work and original evidence.
6. Save a non-sensitive result summary and exact resume instructions; commit/push repository documentation. Keep original county data, tokens and private receipt bodies out of Git.

## Acceptance boundary

A successful run proves fresh supervised index capture and production handoff for this bounded window. It does not prove full notice extraction, complete property qualification, an unattended wake, PropStream processing or SMS delivery. Recurring schedule activation requires a separate decision after reviewing this result. The existing cumulative $50 tracing cap remains unchanged and unused by this cycle.

## Progress

- [x] Current collector supports explicit production routing and source-scoped credentials.
- [x] Existing heartbeat is paused; no replacement worker is required.
- [x] Historical single-record acceptance already proved HTTP acceptance and exact replay behavior.
- [x] User authorizes this new bounded cycle while collection is paused.
- [x] Shared claim state and browser access verified for this cycle.
- [x] Both fresh inventories saved, validated and accepted with gates reclosed.
- [x] Production receipts and unchanged sending/spend controls verified.
- [ ] Separate unattended scheduling decision made from observed results.

## Result

Completed 23:19 UTC October 16: Dallas run 016cb8cb-435a-4859-a7da-4abb270fa643 accepted 25 notices; Collin run ba34b741-b75e-4591-b923-63fa4c7b26df accepted nine. Each has one durable batch, matching receipt hashes and previously unseen official IDs. Daily Lists shows 34 new notices awaiting verification, plus 570 earlier notices. No CRM lead/property/task or tracing count changed. SMS fingerprint unchanged; all intake gates, spending/outreach and SMS scheduler are off. Recurring heartbeat remains paused.

Raw capture and receipt evidence is preserved privately in work/bounded-collection-20261016/. Do not repeat this completed operation or reset the consumed daily claims. Full notice extraction and property/current-sale evidence remain required before CRM association.
