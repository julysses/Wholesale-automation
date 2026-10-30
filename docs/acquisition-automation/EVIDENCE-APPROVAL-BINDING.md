# Supporting-file to content-review binding

Implementation contract, October 30, 2026. This document preserves the next work beyond the completed read-only scan-status increment. It is not production migration or file-use approval. The original acquisition PRD remains controlling.

## Current source findings

- `20261029013306_acquisition_mail_content_reviews.sql` stores immutable content decisions with a supplied artifact UUID and hash, but does not resolve them against registered files or trusted scan observations. Existing records are historical attestations, not verified file bindings.
- `20261030182649_acquisition_content_review_session_freshness.sql` is the latest proposed review-function implementation. Preserve its wall-clock session checks after content locks and immediately before insertion, including exact retries and withdrawals.
- `20261030171809_acquisition_evidence_scan_state.sql` returns a read-only statement snapshot. It checks registry policy, observer/session/key validity and sticky workspace-wide detection for matching bytes. It never permits preview, content approval or execution. Do not use its response or a browser-selected status as transaction authority.
- `20261029184129_acquisition_evidence_attestations.sql` serializes on verification ID and artifact ID. It does not yet serialize different artifact IDs containing the same bytes. A content approval checking only one artifact lock could race with a detection on a second artifact.
- `private.acquisition_mail_content_state` determines whether a review remains current; `private.acquisition_mail_proof_context` depends on that state. Both must reject old unbound approvals after the binding migration, while retaining their readable history and allowing authorized withdrawal.
- `ContentReviewRecord` is an exact server response schema. Avoid adding fields to its `to_jsonb` record unnoticed. A separate immutable binding relation can preserve current response shapes and avoid rewriting historical reviews.
- The current app puts supporting files within step 3, alongside content review. Preserve that location, existing saved-request recovery, scoped campaign selection and navy/orange hierarchy.

## Proposed data and access changes

Use an additive immutable relation tying one content review to the exact artifact, SHA-256 and signed verification ID, with workspace/campaign scope enforced by composite references. Do not backfill historical attestations as verified bindings. Keep bindings private with RLS and no direct application writes; return only approved projections through existing authorized functions. Retain all old review, audit and scan rows.

New approval requests must resolve the selected file in the same workspace/campaign, for mail-content purpose, with an exact expected hash, current retention policy and an eligible trusted observation. Approval expiry must fit the evidence and destination validity limits. Withdrawals retain original review evidence and remain possible while acquisition activation is disabled. Exact retries reconcile the original record with current actor authority and do not turn a historical receipt into current approval.

The write must store the immutable binding and existing review/audit atomically. Include the bound verification identity in audit evidence without exposing signing material or raw scan payloads. Keep `execution_authorized=false` in every review receipt.

## Concurrency requirements before implementation

1. Extend attestation recording and the eventual approval write to share a workspace-plus-SHA-256 advisory lock. Use the same artifact-before-byte-lock order everywhere. Registration and revocation retain artifact serialization. A new alias cannot bypass an existing detection hold.
2. Inspect the complete existing lock order before inserting this lock into review, scan and future clearance paths. Preserve existing activation/workspace/actor authority locks, template/destination locks and exact-request serialization. Do not introduce an inverse dependency between review and verification writers.
3. Lock the referenced policy, signer and observer membership/profile/session while evaluating approval. Re-read immutable observations after acquiring serialization locks. Use wall-clock time after all waits; do not rely on transaction-start time or the UI's 30-second snapshot.
4. Re-evaluate exact artifact/hash/purpose, revocation, retention, current trusted observation and any detection for matching workspace bytes immediately before inserting the bound decision. Roll back the whole decision if any check changes or expires.
5. Current-state reads must require the stored binding and still-current evidence, in addition to existing template/destination/reviewer checks. Invalidating a key, observer, file, policy or applicable hold removes current approval and internal proof availability; it does not erase history.

## Detection clearance remains a separate reviewed action

Do not implement clearance as deleting a detection, toggling an artifact flag, uploading another copy or accepting a later clean scan. A future clearance needs immutable documented administrator review under an explicitly configured policy, exact detection-set identity, suitable newer verification and an expiry/revocation path. It must use the same byte-level serialization. Until that lifecycle is implemented and reviewed, recorded detections remain held. Healthy-file approval must not silently introduce a clearance override.

## App handoff

Replace the manual reference/digest entry with selection of a registered supporting file after the backend binding is enforced. Show the plain file type/date/status and one next action; keep technical references expandable. The server must independently verify the selected identity and digest at save time. A scan result alone cannot enable mailing or a binding offer. Preserve the exact pending content request through a lost response, access loss and page reload; never silently swap its evidence file on retry.

The supporting-file status panel is read-only and already implemented. Selection, transaction binding and clearance are not complete. File-byte preview needs its own guarded access path and is not authorized merely by this plan.

## Required evidence for completion

- Current full-schema inventory, CLI-created forward migration, entity mapping and compensation procedure; all prior data/ACL/RLS preserved.
- Historical unbound approval retained but no longer current; authorized withdrawal and exact historical retry retain correct semantics.
- Healthy signed evidence binds one exact approval, while unregistered/wrong-hash/wrong-purpose/wrong-workspace/expired/revoked/held evidence cannot bind.
- Actual database contention: detection on the same artifact and on an alias; policy/key/session expiry or revocation during lock wait; concurrent approval/withdrawal; exact retry and changed reuse. No deadlocks, duplicate decisions or extra audit rows.
- Actual local PostgREST and application round trips; strict response schemas; no authority leak to operator/caller/service roles or another workspace.
- Browser verification of file selection, stale status, expiry, held evidence, pending-request recovery and next-step guidance in the existing process.
- Full predecessor CI success before feature push, exact successor CI verification and separately approved hosted/platform acceptance. Local test success is not production activation.

Compensation must use a reviewed forward change that disables/revokes the affected write entry points while preserving decisions and bindings. Never compensate by restoring approval based solely on a user-supplied evidence reference.
