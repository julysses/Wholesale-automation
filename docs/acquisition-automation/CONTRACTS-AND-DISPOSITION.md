# Acquisition contracts and disposition

October 31, 2026. Local implementation checkpoint, not legal approval or execution authority.

## Implemented review rules

`schemas/acquisition_contracts.py` and `tools/acquisition_contracts.py` define a typed, pure review of a trusted repository snapshot. No endpoint accepts these assertions, no SQL is changed, no contract state is persisted, and no agreement/package is sent. The result always sets execution_authorized=false. A ready_for_review result is an internal review outcome only.

The transition graph follows draft → pending_signature → executed → title_review → disposition_review → assigned_or_direct_close → closed. Cancelled and expired are terminal. Disputed is an exception state that can return to title review only with current dispute-resolution evidence, or enter a separately reviewed cancellation/expiration path. No automatic date-based cancellation or expiration is inferred.

Evidence must match workspace, contract and version, be current and unrevoked, and identify its human reviewer. Assignment documents and approvals are bound to the selected buyer/closing structure. Unknown assignment provisions require review. Entering disposition review does not require a buyer; advancing to assignment does. Principal acquisition has its own requirements and does not require assignment documents. Deadline changes require a new reviewed contract version; stale snapshots cannot support progress. Confirmed closings can be reconciled after the original deadline without fabricating an extension.

Fifty-four local tests cover terminal/exception transitions, review ordering, stale evidence/snapshots, mismatched identities, buyer changes, separate exit paths, missing/invalid dates and fields, and absence of execution authority. These tests do not establish enforceability, legal sufficiency, actual signatures, title clearance or transaction completion.

## Required persistence and security work

1. Reinspect live metadata, migrations, constraints, grants and RLS before SQL. Reuse existing deals, buyers, buyer_preferences and acquisition owner/property/offer references where their semantics match; logical contracts/disposition must not create parallel buyer or property systems. Current source search found no acquisition contract_status/disposition_review/assignment_allowed implementation. Historical catalog mapping is not a fresh production inventory.
2. Persist immutable contract versions, executed-document references, effective/inspection/closing dates, earnest money and assignment provisions. Store actual evidence references and reviewer decisions, not caller-supplied approval booleans. Bind evidence to exact file bytes/current retention and access controls.
3. Provide workspace/role/MFA-checked RPCs with exact-request idempotency, expected-version concurrency, immutable audits and deterministic locks. Reload authorization, evidence, holds and deadlines after waits. The pure helper is not an authorization service; SQL must enforce the persisted transition invariants independently.
4. Record title/contract/assignment-basis reviews, counsel-approved disclosure templates and delivery evidence. Define evidence applicability/expiration rules with reviewed policy; the helper supplies no legal durations or Texas-law determination. Bind assignment approval to the actual proposed assignee and structure. Enforce a separate gate before distributing any buyer package.
5. Extend existing buyer records with workspace isolation and reviewed buy boxes/closing capability. Match buyers within authorized cohorts. A match is not consent to contact or permission to distribute. Buyer packages must accurately describe Hilltop's contractual interest and reviewed facts; no implication of legal title ownership.
6. Persist assignment agreement, deposits, closing milestones and expense/net-proceeds reconciliation. Unknown signing/payment/closing outcomes remain held until reconciled. Extend attribution to the actual closed transaction.
7. Test exact retries, concurrent evidence revocation/contract edits, tenant/session boundaries, exception recovery and actual app-to-database journeys. Only then integrate the UI and request any necessary hosted or execution approval.

## One guided app process

Continue the current acquisition review page after proposed-amount review: contract documents → title review → choose direct purchase or assignment → closing. Preserve property/seller context and the navy/orange numbered cards. Show missing evidence/deadlines and one next action in plain language. Put document/version details behind supporting detail controls. Saving a review must not appear to sign an agreement, clear title or distribute a package.

No production migrations, signatures, marketing, seller/assignee communication, money movement or closing changes are authorized by this implementation. The original PRD and all sequential channel release gates remain controlling.
