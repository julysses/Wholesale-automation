# Postal eligibility and persisted mail batches

Design checkpoint from current source inspection. Not a migration, policy or release approval. The complete PRD and sequential activation gates remain controlling.

## Current gap

The pure proposal builder in tools/acquisition_mail.py does not read canonical records, reserve budget or create mail jobs. Its trusted-snapshot ALLOW input is not execution authority. acquisition_contact_points currently supports phone/email only; private.evaluate_acquisition_eligibility explicitly blocks direct-mail contact compatibility. Owner/property assertions remain unverified. No saved campaign or content review can currently establish mailing readiness.

## Required implementation order

1. Inspect fresh production function bodies, constraints, policies, grants and migration ledger before additive SQL. Use the CLI migration command and update the reviewed manifest/full-catalog rehearsal. Reuse ad_campaigns, ad_creatives, workspace_leads, acquisition_owners, contact provenance, suppression and decision ledgers; do not build a parallel owner/campaign system.
2. Extend typed endpoints with structured postal observations. Preserve raw source, provider result, evidence reference, unit, normalization version, checked/expiry times and verification outcome. Provider validation establishes deliverability only. Missing/ambiguous units, unknown/deceased owners and unclear authority require review. Raw string normalization cannot grant verified identity.
3. Canonicalize only reviewed validation output; retain aliases and provider identity/version. Shared addresses must not merge people or properties. Check matching endpoint/owner restrictions privately across workspaces without exposing unrelated identities.
4. Extend shared direct_mail eligibility using server-loaded inputs, current policy, scope and expiration. BLOCK/REVIEW deny execution. Any ALLOW path requires an approved policy and current evidence; a form submission or caller-supplied boolean cannot supply it. Preserve phone/SMS behavior and recheck at reservation and dispatch.
5. Persist proposed batches/jobs with immutable campaign/template/content/destination/evidence/quote/recipient-decision snapshots and complete history. Client requests identify records plus an idempotency key, never verification, historical spend or eligibility assertions. Proposals do not reserve funds or dispatch.
6. Reserve only in a separate approved transaction: lock campaign budget and canonical property/destination cadence in deterministic order, revalidate sources, account for lifetime committed costs and reserve all jobs atomically. Exact retry returns the original result; conflicting retry fails. Unknown/submitted outcomes retain reservations until authoritative non-fulfillment evidence. A timeout is not release evidence.
7. Implement the selected vendor adapter behind disabled configuration, with stable idempotency identity, exact request hash, authenticated webhooks and immutable reconciliation. Sandbox/proof validation precedes separately approved fulfillment. No live endpoint fallback or inferred vendor selection.

## Same guided app process

Retain message → response destination → content review inside the numbered navy/orange campaign card. Keep technical references expandable. Later continue recipient review → proposed batch → approval → fulfillment tracking in that same campaign context. Use plain statuses and one primary next action. A saved document, reviewed content or proposed batch must not imply fulfillment approval. Preserve exact pending requests across refresh and navigation.

## Acceptance required

- Full-schema upgrade preserves legacy CRM/county/SMS history and phone/email behavior.
- Role/session/RLS isolation for postal data and batches, with no caller approval/policy access.
- Distinct units remain distinct; same-property/equivalent-destination duplicates cannot produce repeated pieces; unknown/deceased owners remain held.
- Cross-workspace suppression blocks without leaking identities. Expired/revoked evidence invalidates stale preparation.
- Concurrent reservations cannot overspend or exceed cadence; batch failure is atomic and retries are idempotent.
- Duplicate/changed webhooks, vendor timeout and partial reconciliation cannot create extra pieces or release uncertain reservations.
- Browser QA verifies connected steps, errors, empty states and pending-request recovery. Vendor sandbox evidence and separate campaign approval precede fulfillment.

Next: fresh dependency inspection and additive postal observations/canonical identity, before exposing batch preparation through an API. No production migration or mailing is authorized by this document.
