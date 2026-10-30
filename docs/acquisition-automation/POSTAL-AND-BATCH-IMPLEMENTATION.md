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

## Postal provenance increment

Local migration `20261030041400_acquisition_postal_observations.sql` adds an immutable, workspace-scoped observation tied to an existing owner/property relationship. It copies only `leads.owner_mailing_address`, preserving exact text, source evidence and SHA-256. Missing or oversized source values fail; the property address is never a fallback. Imports require current owner/admin/operator membership, MFA and an active session. Authority rows are locked and session expiry is rechecked after potential source-row waits. Raw writes and service-role imports are denied; exact-ID retries return the original historical evidence without conferring permission or verification.

This is provenance, not a canonical verified endpoint. Provider validation, structured address/unit parsing, aliases, postal suppression integration, legal policy, batch reservations and fulfillment remain to implement. The new relation extends the existing owner/property graph instead of creating a second owner database. No UI import action is exposed yet.

Compensation: keep acquisition activation and future postal import routes disabled. If needed, revoke authenticated EXECUTE from the new public/private import functions through a reviewed forward-only migration, while retaining rows, hashes and audit history. Do not drop observations, clear suppressions or enable another sender. Existing phone/email normalization, policies and SMS scheduling are unchanged. Production application of this migration requires explicit approval of the exact candidate and evidence.

Fresh read-only metadata at 2026-10-30T04:13:11Z confirms the separate owner mailing-address field, property unit fields, unchanged latest production migration 20261023221455, and absent acquisition tables in production. Saved under evidence/2026-10-30-postal-source-inventory.json; no customer rows were read.


Postal concurrency/transport follow-up: real signed PostgREST requests now verify exact parallel import convergence (one row/audit), source/unit preservation, tenant isolation and session expiry during an observed activation lock wait. The original local candidate accepted the expired session; acquiring activation before the final expiry check corrected it. The final run passed ten real HTTP checks plus all 46 migrations and 48 application journeys. Evidence: evidence/2026-10-30-postal-http-result.json. This is local transport evidence, not hosted Auth issuance or provider address verification.

## Guarded application handoff

The postal-observation POST route imports only an existing workspace owner relationship and a stable request ID. ACQUISITION_POSTAL_IMPORT_ENABLED defaults off. It returns the original unverified observation on exact retry, hides internal source evidence, validates receipt scope and denies execution claims. This is backend preparation, not a new operator step. Canonical validation, shared suppression/eligibility and vendor selection remain prerequisites to recipient selection in the existing guided app. Local coverage is recorded in evidence/2026-10-30-postal-api-result.json.

### Confirmed provider preference

User confirmed PropStream for address verification/skip trace, with no letters/postcards provider selected. Treat PropStream as the intended data source; verify the actual available export fields and evidence before classifying an address as deliverable. A returned address alone must remain unverified. Provider purchases, live lookups and fulfillment are not authorized by this preference. Next inspect the existing PropStream import mapping without ordering data, then map source and verification evidence into the shared postal workflow.

Existing source inspection: frontend/src/lib/propstreamResultMatch.ts maps owner plus full property address to returned phone/email contacts; it has no postal-verification fields. frontend/src/lib/propstreamBulkCsv.ts deliberately leaves mailing-address export columns blank rather than substituting property address. Preserve both behaviors. A future PropStream postal import needs explicit source-column mapping and evidence handling; the current contact matcher does not prove postal deliverability.

Provider documentation checked October 30, 2026: [PropStream FAQs](https://www.propstream.com/faqs) describe skip-trace phone/email results; [direct-mail guidance](https://www.propstream.com/news/propstreams-new-direct-mail-experience-connect-track-grow) describes mailing-address export and returned-mail handling. These pages do not establish a supported verification API or an authenticated deliverability evidence format for WholesaleOS. Keep provider adapters disabled until the actual integration contract is verified; no guessed endpoint or automatic promotion from an exported address.
