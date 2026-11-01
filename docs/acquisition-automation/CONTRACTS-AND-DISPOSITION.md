# Acquisition contracts and disposition

October 31, 2026. Local implementation checkpoint, not legal approval or execution authority.

## Implemented review rules

`schemas/acquisition_contracts.py` and `tools/acquisition_contracts.py` define a typed, pure review of a trusted repository snapshot. No endpoint accepts these assertions, no SQL is changed, no contract state is persisted, and no agreement/package is sent. The result always sets execution_authorized=false. A ready_for_review result is an internal review outcome only.

The transition graph follows draft → pending_signature → executed → title_review → disposition_review → assigned_or_direct_close → closed. Cancelled and expired are terminal. Disputed is an exception state that can return to title review only with current dispute-resolution evidence, or enter a separately reviewed cancellation/expiration path. No automatic date-based cancellation or expiration is inferred.

Evidence must match workspace, contract and version, be current and unrevoked, and identify its human reviewer. Assignment documents and approvals are bound to the selected buyer/closing structure. Unknown assignment provisions require review. Entering disposition review does not require a buyer; advancing to assignment does. Principal acquisition has its own requirements and does not require assignment documents. Deadline changes require a new reviewed contract version; stale snapshots cannot support progress. Confirmed closings can be reconciled after the original deadline without fabricating an extension.

The local rules tests cover terminal/exception transitions, review ordering, stale evidence/snapshots, mismatched identities, buyer changes, separate exit paths, missing/invalid dates and fields, and absence of execution authority. These tests do not establish enforceability, legal sufficiency, actual signatures, title clearance or transaction completion.

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

## Verified persistence design checkpoint

Fresh metadata is now captured in SCHEMA-MAPPING.md and the October 31 contract catalog/function evidence. The next migration must extend canonical deals, not create an acquisition_contracts parent with a second deal identity.

First persisted slice: a disabled workspace-bound draft contract attached to the existing lead/property/owner and reviewed-offer identity, with immutable version and exact creation receipt. Explicit nullable acquisition fields must leave all legacy rows unchanged. Define composite parent keys so a deal cannot combine workspace, lead, property, seller or offer from different contexts. Draft creation must not imply the internal amount approval authorized a binding offer.

Use existing application identity/session/MFA helpers, owner/admin/operator draft permissions and narrower owner/admin approval permissions. Lock the canonical lead/deal and recheck after contention; reconcile exact request identity before issuing another draft. Preserve one active deal per lead across acquisition and legacy creation. Hold conflicting existing legacy deals for review instead of auto-adopting their claimed contract state. Restrict raw service-role writes on acquisition-bound rows and guard the old/new parent on reassignment.

Store contract terms with their source precision and immutable document evidence. Extend the current timestamp-only pure reviewer before adapting legacy date-only terms; unknown cutoff times must remain unknown. Project acquisition state into legacy stage only through an explicit mapping: review is not buyer marketing, principal closing is not assignment, and disputed is not closed/cancelled. Preserve legacy validators unchanged for unscoped records, and make the acquisition path enforce its own complete rules.

Required first-slice tests: exact create retry/conflicting reuse, two simultaneous drafts for one lead, legacy/acquisition creation contention, mismatched seller/property/offer, current/revoked session and membership, caller/agency denial, direct/legacy service-role write denial, no implicit historical adoption, and unchanged populated legacy deal/task behavior. Follow with evidence registries and transitions, buyer isolation/matching, disclosures/packages and actual app journeys; the draft alone does not close DISP-001–010.

## Local draft persistence candidate

Migration `20261031221633_acquisition_contract_drafts.sql` now implements the first draft slice described above. Canonical `deals` rows remain in `offer_made` with `acquisition_status=draft`; contract prices, dates, buyer and signed-document links are not fabricated from the reviewed proposal. Composite keys bind the workspace, lead, property, reported seller relationship and offer. The reported seller association is not title verification.

`create_acquisition_contract_draft` accepts only record identities, the expected offer-review sequence and a draft name. It derives the actor/session, requires MFA, serializes with legacy deal creation and offer review, rechecks current approval/property, and preserves one exact receipt. Exact authorized recovery can report a historical save after activation/approval changes; it cannot authorize another action. Immutable version/audit rows preserve the request. No transition beyond draft is exposed in this migration.

Six focused database tests, three observed expiry/revocation lock waits, and the full 57-migration rehearsal passed. Current gateway evidence covers canonical draft save/recovery, seller joins and tenant isolation. The guided fifth step is implemented with separate synthetic browser evidence; hosted acceptance remains required. Compensation is to disable acquisition activation and preserve rows, versions and audits; no destructive rollback is proposed.

## Authenticated API and contention verification

Mounted POST/GET `/api/acquisition/workspaces/{workspace_id}/contracts/drafts` reuses the existing user-JWT store. Save input has exact request/offer/relationship references, expected offer sequence and draft name; it accepts no claimed actor, workspace override, execution approval or contract terms. Returned receipts and paginated rows are validated before display. Save uncertainty requires the same request/details; no automatic retry, provider contact or signed-contract assertion occurs.

483 contract/API/auth regressions passed; the mounted-router-specific suite also passed (90 tests including pure rules). Three real observed lock waits rejected sessions, memberships or approvals revoked during serialization. Full catalog rehearsal initially rejected an incorrectly seeded historical fixture; corrected fixture seeds the legacy row before binding and retains the guard. The corrected run passed: 57 migrations, 26 access probes, 88 workflows and 54 actual local gateway checks. The fifth guided screen passed synthetic desktop/mobile and reload-recovery QA; these results do not establish hosted Auth acceptance.

## Date precision and guided review checkpoint

The pure review helper is now version `acquisition-contract-review-v2`. It preserves explicit calendar dates separately from known instants for effective, inspection and closing terms. A term cannot claim both representations. Calendar fields reject datetime/numeric values and timestamp strings; no midnight/timezone is synthesized. Results identify instant/date/unknown precision. Date-only terms hold normal forward progress for review under an approved interpretation; an evidence-supported exception review can still proceed without inventing a cutoff or automatic expiration. This is not a legal cutoff policy and is not yet a persisted document/term update endpoint.

109 contract/API tests passed after adding nine precision/coercion/exception cases. Next persistence increment must bind each term and its precision to exact access-controlled source documents and immutable contract versions, enforce reviewed evidence and authorized transitions in SQL, and expose those missing-evidence steps through the same app process.

## Human review persistence checkpoint

Candidate migration 64 now stores exact human review bindings for contract review, title review and assignment basis, with immutable decisions, current-state assessment and original-reviewer withdrawal. It does not establish legal sufficiency or execute any contract transition. Reviewer policies remain empty by default. API/interface integration, controlled policy provisioning, immutable terms and persisted transitions remain required; see CURRENT-STATUS.md for validation and publication status.
