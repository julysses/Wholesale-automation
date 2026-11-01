# Title findings after recorded execution

Status: candidate95 defines and tests the input/assessment boundary. Persistence, API and guided form remain to implement. No title approval or disposition authority exists from these new modules alone.

## Operator workflow

Continue the existing step5 property/contract context:

1. Begin title review from the recorded execution handoff.
2. Retain the original title report and supporting documents; verify their original bytes and current source authority.
3. Record the report cutoff at its original precision, plus findings for ownership, legal description, liens/payoffs, exceptions/encumbrances and occupancy/possession.
4. For each finding, retain its original page/clause, explanation and immutable source identity. Unknown and unresolved items need a concrete next action; they cannot be silently omitted or treated as satisfactory.
5. Record either a resolution hold or a personally reviewed approval with bounded validity. A hold has no approval expiry and cannot satisfy a disposition gate. A reviewer may hold even apparently satisfactory findings for an additional issue explained in the decision note.
6. Preserve original withdrawal and exact-request recovery. Only a separately controlled disposition review may consume a still-current title decision.

The UI must keep the existing navy/orange card style, explicit stage headings, source choices, recovery holds and mobile layout. Starting title review, storing bytes, passing a scan and recording a human finding are distinct events. None alone establishes legal title or authorizes marketing, assignment or closing.

## Input boundary implemented

- `schemas/acquisition_title_review.py`: bounded immutable original references; all five finding categories required; source-backed satisfactory findings; explicit required actions for unknown/unresolved findings; report cutoff preserved as unknown/date/instant; no future-version or conflicting-original citations; personal review and separate approved/held/withdrawn envelopes.
- `tools/acquisition_title_review.py`: reason codes and unresolved actions. Outputs always deny legal/title/execution authority and require source verification, report freshness review and recorded-execution binding. An explicit future instant is held; calendar dates are never silently converted to midnight.
- `tests/test_acquisition_title_review.py`: missing/negative findings, source conflicts, scope-related version bounds, coercion/authority injection, cutoff precision, future instant, immutable payload, explicit holds and original withdrawal.

These inputs are assertions for a reviewer. No client-supplied actor, execution-transition identity, approval flag or source verification can create authority.

## Required persistence and server controls

Use the existing `acquisition_contract_reviews` entity with a distinct `title_findings` kind. Preserve the generic preparation-stage `title_review` records. A preparation approval must not satisfy post-execution disposition merely because it remains unexpired.

1. Inspect current columns, constraints, indexes, RLS and migration history; create an additive migration via the CLI. Keep policy/FK/immutable audit identities and actual workspace/session/MFA/role checks.
2. Add bounded findings and server-derived original-source journal fields. Bind every recorded decision to the exact sequence2 executed transition for the current immutable contract version and its retained execution review. Confirm the current sequence3 title-review context when creating a new decision. Use scoped foreign keys and controlled checks rather than a client-provided execution identifier.
3. Add `requires_resolution` only for this new kind: personally reviewed, no approval expiry, retained findings/actions. Other review kinds retain their current approved/withdrawn contract. Withdrawal retains original decision identity and does not replace findings. Existing generic RPCs continue to reject this kind and status.
4. Require a separately reviewed `title_findings` policy for the selected title report and authorized reviewer. Do not inherit a preparation policy or seed authority. Counsel-approved report freshness/timezone rules remain explicit; do not infer a cutoff instant from a date.
5. Resolve the selected title report and every supplemental source against the exact workspace, contract, source version and hash. Retain original verification/scanner/session/policy/retention identities; deduplicate locking by original artifact while retaining each page/clause citation. No source may be substituted by a later scan or newer document on retry.
6. Lock current contract/history, artifact and byte identities, verification/scanner/retention policies, original reviewers and sessions, execution authority and bound deadline authority in the established deterministic order. Recheck after waits with current time; require current review only for new authority, not as a way to erase historical receipts or deny original withdrawal.
7. Fingerprint the full exact request and actor/session. Persist one immutable decision and audit in one transaction. A held or withdrawn latest decision invalidates the older approval. Historical receipts are non-executing; fresh state must independently recheck all original authority.
8. Only then mount the user-JWT API and bounded source/policy discovery, implement browser recovery and the guided findings form, and bind disposition snapshots to this exact current post-execution review. Never map an ordinary preparation review directly to disposition authority.

## Required verification before release

Disposable upgrade preserves representative history and Storage. Test approved/held/withdrawn history, exact concurrent retries, changed-payload conflicts, workspace/role/MFA/session isolation, original source revocation and replacement, report precision and policy freshness, execution/deadline revocation during observed lock waits, and no raw writes. The mounted API journey must include response loss, historical retry after pause and current-authority invalidation. Desktop/mobile QA must cover unresolved actions, source citations, no automatic positive defaults, fresh checks, original withdrawal and recovery without the currently selected proposal.

No production migration, policy provisioning, outreach, paid fulfillment, agreement execution or disposition distribution is authorized by this plan. Full PRD scope, all channel gates and hosted/provider/legal acceptance remain open.


## Storage implementation checkpoint — November 1, candidate96

Migration `20261101055752_acquisition_title_findings_storage.sql` extends the existing immutable review and policy entities; it does not create a parallel title system. The distinct `title_findings` kind supports approved, requires_resolution and withdrawn records. The exact workspace, contract version and executed transition are bound by foreign key; a title-entry transition cannot substitute for execution. Withdrawal references an original approved or held finding in the same execution context. Findings and source journals are bounded and preserve original citations, unknown/date/instant cutoff precision and unresolved actions. Generic preparation review RPCs remain closed to the new kind.

The source journal is structural evidence storage, not a current verification service. Supplemental-source authorization, freshness, post-lock rechecks, current sequence3 context, original execution/deadline authority, retries, API/discovery and guided findings UI remain required before this path is usable. No policy or approval authority was provisioned. Existing RLS, MFA/role access, immutable history and direct-write restrictions remain in place. Compensation is to keep this path unavailable or pause acquisition while retaining all history; do not delete reviews or reverse migrations.

Pre-migration local columns, constraints, indexes, grants and RLS inventory is retained in `evidence/2026-11-01-title-findings-local-catalog.json`. Validation and publication results are recorded in CURRENT-STATUS.md and PROGRESS.md. The app remains at the existing step5 title-document intake until the controlled findings workflow is completed; no user-facing clearance or distribution capability is introduced by storage alone.


## Original-source resolver — candidate97

`private.resolve_title_review_sources` in `20261101061021_acquisition_title_source_resolution.sql` implements the current original-source portion of item5 above. It has no application grants and writes no records. A controlled owner-context caller must use it within the same transaction as the review write. It acquires current contract/session/activation and source locks, preserves exact original scan identities in a bounded journal, and checks source authority after waits. Its returned deadline bounds sources and the current actor session only. It does not establish execution, human review, report freshness or legal/title authority.

The writer must derive the executed transition and its exact review from server history, lock/revalidate execution and deadline authority, obtain the separately reviewed title-findings policy and report freshness decision, and recheck the retained source journal at the final write time after all additional waits. Do not interpret a successful resolver response as permission to approve, distribute, assign or close. Missing or revoked sources are held; a historical receipt or original withdrawal must not rerun this new-authority resolver as a prerequisite to recovery.

Security review: private INVOKER function, fixed empty search path, no public/anon/authenticated/service-role execute grant, existing actual membership and auth.sessions checks, no user_metadata authorization, no Storage/public-client secrets or new tables. Compensation: leave the title writer unavailable and retain all evidence/history.


## Controlled decisions and current status — candidate98

Migration `20261101061744_acquisition_title_review_write.sql` supplies `record_title_review` and `title_review_state` with public INVOKER/private DEFINER wrappers, fixed search paths and authenticated-only execution. The actual owner/admin membership, MFA and live session checks remain server-side. A source resolver success is now combined with recorded execution/title entry, original execution/deadline authority and a separately reviewed title policy before approval can be persisted. Final current-state validation occurs in a separate statement after the insert, inside the same transaction; failure rolls the write back. The complete policy row is retained as `title_policy_snapshot` and must still match for current approval.

Policy freshness fields: `title_report_max_age_seconds` for explicit instants, or `title_report_max_age_days` plus `title_report_timezone` for calendar dates. Missing fields authorize neither precision; the policy may explicitly support one or both. Calendar age compares actual local dates and computes only a policy validity boundary, never a replacement report timestamp. Unknown cutoffs and unresolved findings can be retained as resolution holds, without approval expiry. The chosen policy still must be current and authorized for the reviewer. New findings require current verified originals; historical retries and original withdrawal do not rerun new-authority resolution.

Private review policies add only nullable fields with shape constraints; public reviews add an optional bounded-kind policy snapshot. Existing stored fixtures or historical rows with no snapshot never qualify as current title approval. No policy is provisioned and no existing review is rewritten. Source/version/execution foreign keys, immutable rows, RLS, raw-write denial and the legacy preparation-kind rejection remain intact. Forward compensation: pause acquisition or revoke policy, retain all decisions and audit events, and leave later distribution disabled.

Remaining: typed application routes/models, current policy/source discovery including original withdrawal target, guided findings UI and recovery, full HTTP application/browser QA, title-based disposition requirements and approvals. The RPC is a reviewed-decision recorder, not proof of legal title or execution authority. Production application and live legal-policy approval remain separate gates.
