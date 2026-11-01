# Next increment: evidence-based buyer review and matching

This is the implementation continuation after the scoped-profile batch is verified and pushed. The complete PRD and sequential activation gates remain controlling; saving a profile is not completion of DISP-004–010.

## Current source findings

- `buyers` is the canonical investor record. Private `acquisition_buyer_versions` fixes exact self-reported input and provenance at a workspace/revision. Matching must bind the reviewed revision, not a mutable name, phone or legacy POF flag.
- `acquisition_evidence_artifacts` is already shared by mail and contract documents. `20261031224723_acquisition_contract_document_registry.sql` explicitly separates campaign ownership from contract/version ownership. It does not support independent buyer evidence. Do not invent a campaign or contract to fit buyer financial evidence into the old shape.
- The evidence registry already has immutable revocations, retention policy references, content hashes, protected uploads and verification. Review current policies, constraints, upload-slot ownership, verification attestations, scan observations and legacy route filters before extending it. Some existing artifact reads permit operators; buyer financial evidence needs its own reviewed access boundary rather than inheriting broad contract permissions.
- Existing `buyer_preferences`, `deal_matches`, `buyer_transactions`, `buyer_outreach_log`, `deals.buyer_id` and `tasks.buyer_id` have a deliberate scoped-buyer guard. Controlled writers must establish matching workspace identities before allowing new relationships. Do not remove the guard globally.

## Required outcome

An authorized owner/admin can review an exact buyer profile and actual retained evidence, record bounded findings about identity and closing capability, and withdraw/revoke that review. A profile edit, expired evidence, revoked reviewer/session or withdrawn finding must invalidate current matching authority while preserving history. Self-reported budgets remain distinct from independently supported purchasing capability. No checkbox or imported legacy `pof_verified` flag is sufficient evidence.

After the contract has a current disposition handoff and reviewed assignment/principal basis, the app can rank same-workspace buyers using geography, property type, price, renovation appetite, strategy and closing capability. Show the reasons, missing inputs and confidence. Unknown criteria must not silently become zero or false. Record the exact profile/review/contract versions used. No ranking or selection automatically distributes a package or grants contact permission.

Then prepare an accurately labeled contractual-interest package and enforce the reviewed seller/assignee disclosures before separately approved distribution. Continue into distinct principal acquisition and assignment agreement/deposit/closing workflows, preserving the canonical deal and all exceptions.

## Implementation order

1. Inventory a fresh disposable current catalog before SQL: canonical buyer revisions, evidence ownership/retention/verification/scan tables and functions, current review policy infrastructure, Storage policies, service-backed readers, and guarded deal/buyer children. Save the mapping and conflicts.
2. Extend existing evidence ownership deliberately for buyer-bound material, or justify a separate private relationship if the registry cannot preserve its existing invariants. Retain exact bytes, provenance, expiry and revocation. Define owner/admin reads and controlled writes; add no activation policy automatically.
3. Add immutable version-specific review findings and a current-authority projection, with exact retries, audit, withdrawal, expiry and concurrent revocation checks. Expose bounded authenticated routes and the next numbered UI step beside the saved profile.
4. Add explainable version-bound investor matching using existing matching logic where compatible, and controlled same-workspace relationship writes. Selection remains review-only until package, disclosure and distribution approval are complete.
5. Test actual gateway and guided desktop/phone behavior, then publish verified increments and confirm all six successor CI jobs before another push.

## Acceptance boundaries

Tests must prove foreign-owner/caller/agency/service/anonymous denial, exact commit-loss recovery, stale profile rejection, revoked/expired evidence and review handling, preservation of legacy buyers/deals, no raw financial-evidence disclosure, and fresh authority immediately before a consequential action. Counsel-approved policies, actual provider configuration, production migration and distribution/transaction approvals remain separate gates. Do not weaken a gate to make a UI action available.


## Fresh disposable inventory before the next SQL increment

`evidence/2026-11-01-buyer-review-local-catalog.json` was captured from the complete baseline plus118 candidate migrations (97886 exit0, `/tmp/buyer-review-inventory.log`). It includes25 tables,461 columns,236 constraints,100 indexes,57 policies,353 grants,26 triggers,69 incoming FKs and60 evidence/buyer-related function definitions/owners/ACLs. This is a separate disposable structural inventory, not a production query or migration-role acceptance result.

Confirmed conflict: raw artifact SELECT currently includes operators, while verification rows permit operators to read their own observations. Buyer financial evidence must not inherit those policies without a buyer-specific restriction. Storage object access already passes through `private.acquisition_evidence_object_access`; inspect and extend that same boundary for any buyer-owned artifact branch. Retain existing object no-replace/no-delete guards and exact admission/retention checks. Existing contract verification key scopes bind workspace/key/purpose; no buyer key scope or reviewed buyer policy is automatically present.


## Legacy matching compatibility findings

Read `tools/buyer_intelligence_engine.py:match_buyers_to_deal` and `schemas/buyer.py` before adapting the engine. The current legacy matcher gives80 ZIP/type points when preferences are empty,40 price points when price data is absent, converts missing numeric fields to zero, and can substitute average purchase price for a stated range. It also mixes legacy IBIE score into fit and emits cash-buyer labels from raw flags. Those behaviors are incompatible with the acquisition requirement to preserve missing data and independently verify closing capability. Keep legacy behavior for legacy workflows; do not expose it as acquisition eligibility or proof of funds.

The acquisition comparison must report each known match/mismatch and each unknown criterion explicitly. Preserve the difference between an empty/unknown preference and a reviewed unrestricted preference; the current profile model only stores the former. Match contract price, repairs and timing against exact reviewed buyer criteria, not inferred averages or permissive percentage tolerances. Keep preference fit, evidence confidence and verified closing capability separately visible. Only the server's fresh review/eligibility checks may decide whether a buyer can advance to selection/distribution. Version the calculation and inputs before adding it to the guarded matching writer.
