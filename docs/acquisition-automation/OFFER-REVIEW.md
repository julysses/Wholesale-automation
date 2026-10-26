# Internal acquisition offer review

Migration: `20261026041236_acquisition_offer_review.sql`. This extends existing `offer_recommendations`; it does not replace legacy recommendations or create a separate offer store. Immutable `acquisition_offer_events` records proposal and review history. No production migration has run.

## Proposal and review

An owner, admin or operator proposes a positive cent-precision amount against an exact saved analysis and explicit base/downside/upside case. The analysis must be the latest revision, calculated, linked to a canonical property, and have a computed offer range. Amounts above that case's computed ceiling are rejected. Lower amounts are permitted; the calculated opening range is guidance, not a mandatory minimum. No amount is copied into the lead's current MAO or offer price.

Only workspace owners/admins can approve the amount or reject a proposal. Approval requires a nonempty review note for each of title, liens, occupancy, valuation, repairs, financing and downside. These notes record the reviewer's judgment and unresolved conditions; their existence does not establish verified title or other property facts. A caller, agency user, nonmember or revoked/expired session cannot approve. An operator may withdraw an open proposal. Approval revocation is owner/admin-only. Actor identity derives from the validated session, never request fields.

Transitions:

- `proposed` → `amount_approved`, `rejected`, or `withdrawn`.
- `amount_approved` → `approval_revoked`.
- Rejected, withdrawn and revoked records remain terminal. Revisions require a new proposal ID.

Every transition has a stable event UUID and expected prior sequence. Reusing the exact UUID/content is idempotent; reusing it for a different decision conflicts. Concurrent decisions serialize and only one can consume the prior sequence. Analysis reservation and approval share the lead's transaction lock, so a concurrent newer scenario cannot race past the approval check. A later analysis revision leaves old approval history intact; that history must never be treated as current transmission authority.

Proposals and amount approvals require database activation. Withdrawal and revocation remain available with activation disabled. Immutable proposal/event protection covers direct service-role writes and old legacy records attached through either the lead or analysis; recommendations with parents spanning workspaces are unreadable. Other unbound legacy recommendations keep their prior behavior. Existing reporting views retain their original column projection; acquisition history endpoints expose the new fields directly under RLS.

## API

All routes use the authenticated user token and existing acquisition feature gate; none uses a service-role fallback.

- POST `/api/acquisition/workspaces/{workspace_id}/offers`: `id`, `analysis_id`, `case`, `amount`, `note`.
- POST `/api/acquisition/workspaces/{workspace_id}/offers/{offer_id}/reviews`: `id`, `expected_sequence`, `status`, `note`, `review_notes`.
- GET `/api/acquisition/workspaces/{workspace_id}/leads/{lead_id}/offers`: bounded UUID-keyset proposal history.
- GET `/api/acquisition/workspaces/{workspace_id}/offers/{offer_id}/reviews`: bounded sequence-keyset decision history.

A proposal ID orders pagination, not creation time. Review sequence orders a proposal's events. A `40001` stale-state conflict returns HTTP 409 asking the client to refresh; no automatic mutation retry is performed. Replayed old review IDs return that historical event, not a claim about the latest state. Consumers must fetch history/current facts before a further transition.

## Remaining release requirements

`amount_approved` is internal financial review only. Responses explicitly state `binding_offer=false` and `transmission_authorized=false`. Approved legal templates, exact seller/document identity, document hashes, expiration policy, final written-offer approval, effective approval invalidation, current scenario selection, approval dashboard and eligibility-controlled delivery remain to be built. No sent status, provider action or contract execution route exists here. Approval identity is session-backed; the future UI must make the intentional human review clear.

Before any delivery, revalidate current analysis, membership/approval authority, property and seller identity, template/document version, approval freshness, unresolved diligence and outreach eligibility. Never authorize delivery from a historical event alone. These remaining controls are part of the full PRD, not optional follow-up work.

## Validation and compensation

Focused local PostgreSQL tests exercise duplicate IDs, immutable history/audit, amount ceilings, cross-workspace reads, limited roles, stale underwriting, concurrency, disabled activation and revocation. The fixture preserves inspected legacy columns/constraints but omits the unrelated qualification/transcript foreign-key chain; full-schema upgrade acceptance is separate. Python tests check user-token transport, input bounds and server-owned actor/status fields.

For compensation, disable new proposals/approvals through activation, withdraw proposals or revoke approved amounts with new immutable events, and retain all prior evidence. Do not delete approval history, relabel old proposals, or drop the migration to undo a decision. No production rollback is currently needed because this migration is local only.

## Current review state and dashboard queue

Migration `20261026041845_acquisition_offer_review_state.sql` adds authenticated read-only projections:

- GET `/api/acquisition/workspaces/{workspace_id}/offers/{offer_id}/state`.
- GET `/api/acquisition/workspaces/{workspace_id}/offers?after={offer_id}&limit=20`.

The current-state response distinguishes `historical_status` from `amount_approval_current`. An amount approval is current only when its last event is approval, its analysis is still the latest calculated property-bound revision, acquisition activation is enabled, and the reviewer remains an approved active owner/admin whose membership has not changed since review. Membership revocation followed by re-enrollment does not resurrect earlier approvals. A newer pending analysis also marks the older approval stale, rather than silently continuing to rely on it. No historical event is rewritten.

The response includes the exact event/sequence, scenario revision versus latest revision, amount, rationale, current blockers and role-appropriate review actions. Those actions are UI affordances; the mutation RPC independently rechecks every transition. A blocked approval may still be revoked. All callers require a current approved operator-or-higher session; callers/agencies and service-role API calls cannot use these projections. The queue is bounded to 50 and uses UUID keyset pagination within one workspace. It includes historical/terminal proposals for review, not only pending items. A full page may return a cursor whose next page is empty.

These are point-in-time dashboard reads, not reusable permission or a lock on future state. `transmission_authorized=false` and `execution_authorization=null` are unconditional. Final document approval, a reviewed freshness/expiry policy and fresh outreach authorization remain required. Profile approval is checked at read time; historical profile suspension/reapproval and document-specific approval invalidation require the later delivery policy. An internal amount indicator must not be relabeled as a send-ready offer. The frontend review screen and current-scenario selection are still pending.

The migration adds read functions and a workspace/ID index only. Compensation is to stop exposing the projections while retaining immutable history; no data backfill or state rewrite is needed.
