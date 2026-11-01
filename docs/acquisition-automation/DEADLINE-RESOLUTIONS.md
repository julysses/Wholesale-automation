# Reviewed calendar-date resolution

Status: typed input and pure comparison implemented locally; persistence, current authority and UI remain unfinished. This does not remove the current execution hold on date-only terms.

## User process

In the existing returned-agreement term review, keep the contract's original calendar date visible. A reviewer may propose an explicit local time, named time zone and UTC offset only with a cited document and an explanation. There is no default time or inferred property time zone. A changed calendar date is an amendment, not an interpretation. Unknown dates must first be established through the ordinary sourced-term workflow.

Separate proposal, human interpretation approval, and execution review. Showing a proposed interpretation never means counsel approved it. A qualified policy must authorize the reviewer and interpretation purpose. Final execution review independently verifies signatures, authority, all terms, every required date interpretation and its original evidence. The recorded contract date remains unchanged throughout.

## Implemented boundary

`schemas/acquisition_deadline_resolution.py` defines one explicit proposed interpretation and exact request version. It requires a matching term/source, original calendar date, local time, named zone, offset-aware instant, stated basis and substantive rationale. It rejects impossible local times, inconsistent date/time/offset/zone combinations, future source versions and client authority fields. Explicit offsets distinguish repeated daylight-saving hours; nonexistent local hours fail validation.

`tools/acquisition_deadline_resolution.py` compares the proposal with server-supplied original terms/current version without mutating either. Only a matching date-only term is eligible for further review. Unknown dates, already explicit instants, changed dates or stale versions remain held. Every result requires source verification and reviewer policy; none grants legal or execution authority. Twenty-five focused cases passed in0.16s, including both fall-back offsets and the spring-forward gap. Full backend validation is logged separately in the current checkpoint.

## Required integration before activation

1. Inventory current schema and create a forward-only migration using the CLI. Extend the existing immutable contract-review entity with a deadline-resolution kind, explicit term discriminator and proposed resolution. Preserve all existing review RPC behavior and row shapes. Use the existing global review sequence plus latest-per-term lookup; do not create a competing contract parent. Approvals and withdrawals both retain the exact term and original interpretation identity.
2. A controlled writer must derive workspace/user/session authority from existing authentication, lock the contract/current version, resolve the original date-only term, then lock its original term evidence and the proposed interpretation source. Require a specifically reviewed interpretation policy. Resolve current source reference, exact scan, retention, scanner/reviewer/session authority and check again after waits. Store exact request identity, immutable source/policy references and audit atomically. Do not provision a policy automatically.
3. Preserve historical exact receipts after expiry/revocation and preserve uncertainty on lost or malformed responses. Withdrawal affects only the original interpretation and never edits the signed date or automatically changes recorded contract status. Another interpretation of the same term needs a new sequence; old decisions remain visible.
4. Read-only discovery should return original date, exact verified source choices, reviewed policy and independent original withdrawal. Current-state checks must require the latest applicable interpretation of each date-only term, matching unchanged current terms/version and all original authority. Expired, revoked or superseded interpretations cannot stay current.
5. Execution findings must preserve calendar precision. Execution review must bind the exact reviewed interpretation IDs used for its date-only terms and load the resulting instants server-side. Require all needed date interpretations; never reuse an unrelated term's approval. Include supplemental interpretation evidence in source locking and current-state checks. Recheck effective time and deadline ordering using those server-derived instants. Explicit-instant contracts retain their existing path.
6. Extend the existing term-review UI with one source-backed interpretation step and current-review summary. Keep context/navigation holds and exact browser recovery. No automatic confirmation, legal conclusion, deadline conversion or status transition.
7. Verify additive historical preservation, tenant/MFA/session boundaries, stale version/date/source rejection, DST validation, independent term withdrawal, full-payload idempotency, concurrent review/withdrawal and expiry/revocation during lock waits. Test actual API committed-response loss and desktop/mobile recovery before any release claim.

## Separate amendment path

Changing a signed date, price, earnest money or assignment provision must not be routed through this interpretation mechanism. A separate sourced amendment proposal, authorized review and immutable version advancement are required. It must preserve signed history, current lifecycle state, original approvals and unresolved external commitments while invalidating superseded current authority. That path remains open work under the full PRD.
