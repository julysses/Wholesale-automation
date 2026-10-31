# Contract document persistence implementation handoff

October 31, 2026. Design and internal transport checkpoint only. No contract upload API, storage authorization, legal review or signing authority is enabled by this document.

## Current verified starting point

Read-only production inspection still reports migration ledger `20261023221455`, canonical `deals`, and RLS-enabled Storage tables. Candidate acquisition evidence/contract tables are absent. Storage object columns include archive/delete-marker/version flags; no Storage object policies were returned by the fresh catalog query. Exact metadata: `evidence/2026-10-31-contract-document-catalog.json`. Reinspect before writing the next migration; local candidate migrations are the intended additive predecessor, not the live state.

Migration 58 extends the existing `acquisition_evidence_artifacts` registry with mutually exclusive campaign and canonical contract-version targets. The mail interfaces remain campaign-bound. Retention policies and revocations support both targets; signer attestations, scan state, content bindings and Storage upload guards still require further contract-specific work. Do not supply a contract UUID in a campaign parameter or create a fake campaign to store contract documents.

`schemas/acquisition_evidence_object.py` now centralizes immutable exact-byte metadata and deterministic object naming. Existing mail descriptors retain required campaign/purpose fields. `ContractDocumentArtifact` separately requires canonical contract ID, contract version and document classification. Both use the same bounded authenticated byte transport, with size/hash/media/retention validation, no redirects, no returned file bytes or URLs, and no approval authority. Internal contract byte observations do not replace registry authorization, scan state or human review.

## Additive persistence changes required

| Existing structure | Required extension | Preserve |
| --- | --- | --- |
| Canonical deals / acquisition_contract_versions | Immutable version identity including workspace; reviewed terms with explicit source date precision | Draft rows, one active deal per lead, legacy unscoped behavior, exact creation receipts |
| acquisition_evidence_artifacts | Explicit contract ID/version target mutually exclusive with campaign target, composite FK to the exact canonical version, bounded document purposes | Existing artifact IDs, mail target/purpose semantics, immutable hash and retention |
| acquisition_evidence_policies | Contract document purposes under explicit reviewed policies | No invented retention period or automatic policy activation |
| Evidence revocations / verification records | Contract target binding and fresh authority; no cross-target attestation replay | Existing mail records and immutable exact retries |
| Upload slots | Generalize the existing per-workspace two-slot admission across both target kinds | One aggregate workspace capacity, fresh attempts, post-wait session/role/retention checks |
| Storage access helper | Dispatch by authoritative registry target; contract version must exist in the same workspace | Fixed bucket/path, no public/signed links, no replace/delete, archived/versioned object denial, mail-only rules unchanged |
| Scan observations | Exact hash/object/target authority and current signer registry | Detection holds across matching byte aliases; later clean observations cannot erase detection |
| Contract review bindings | Exact document IDs/hashes/verification observations, actor/role and contract version | A byte match or document classification never becomes legal approval |

Do not generalize the existing public mail RPC signatures to optional loosely checked targets. Keep their required campaign inputs and mail-only purpose validation. Add typed contract entry points that resolve the target server-side and share the underlying protected artifact lifecycle. All new contract version references require enforced workspace identity; an application filter alone is insufficient.

## Shared upload admission candidate (migration 59)

`20261031225950_acquisition_contract_upload_admission.sql` extends the existing private upload-slot table with an exclusive contract/version target and a composite foreign key to the registered artifact. Mail and contract RPCs use the same workspace advisory lock, two workspace slots, one active reservation per actor, fresh attempts and 120-second expiry. Expired slot reuse clears the alternate target in both directions. No release endpoint or extra contract quota exists.

`admit_contract_document_upload` rechecks current workspace/member/profile/session, activation, exact draft/version, creator, purpose, retention policy and revocation after waiting for capacity serialization. The returned decision grants no Storage or execution authority. The unchanged Storage guard still denies contract uploads; a later complete upload path must recheck authorization immediately before writing and after verification.

Validation is tracked in CURRENT-STATUS.md and PROGRESS.md. Next: strict admission receipt parsing and shared process capacity in the internal transport, guarded Storage dispatch, upload reconciliation, scan/review binding and guided document UI. No HTTP upload endpoint should be mounted before the complete path passes acceptance.

## Transaction and failure behavior

1. Resolve the current authenticated actor, MFA session, workspace membership and authorized role. Draft preparation may use owner/admin/operator; legal/transaction approvals require the separately defined authorized approval roles.
2. Acquire the documented contract/version and evidence locks in one consistent order, then re-read role, session, activation, version, source documents, retention and revocations using the current clock. Test conflict with offer review, draft creation and evidence revocation.
3. Preserve original request receipts. An exact retry reports historical persistence only; it must not infer that a document, review, retention policy, signature or closing remains current.
4. Bind terms to their source document and source precision. Date-only source fields cannot become midnight timestamps or inherited task-reminder times. Unknown assignment provisions remain unknown.
5. Persist immutable version/audit/review records atomically. Reject raw scoped service-role writes and legacy update paths. Do not adopt old unscoped deals or signed links without an explicit reviewed migration path.
6. Treat unknown upload, verification, signature or transaction results as reconciliation holds. No automatic second object/contract/send. No deletion of historical evidence to simulate rollback; disable activation and preserve history.

## Acceptance before exposing document review in the app

- Full migration rehearsal over historical records, with row/definition preservation and compensating procedure.
- Actual JWT/RLS tests for both mail and contract paths: cross-workspace, cross-contract/version, wrong purpose, caller/agency, anonymous, revoked membership/session, service and legacy bypass attempts.
- Exact concurrent registration/retry; shared upload capacity under mixed mail/contract demand; current policy/session expiration after observed lock waits.
- Actual protected Storage authorization and registry-before/after recheck around streamed bytes; mismatched/hash/size/media/redirect/truncated inputs; retention/revocation changes during streaming.
- Signed scan observation replay/binding and alias-detection tests across both target kinds; immutable review inputs and stale-version denial.
- API-to-local-gateway document registration, admission, verification, review and term-version round trip. Hosted Storage/Auth acceptance remains separate and approval-gated.
- Extend step 5 with document upload and clear pending/verified/review-required states. Carry the same property/seller/contract into title review, exit choice and closing. Never present a saved draft or verified bytes as a signed agreement.

Current official private-bucket access model: https://supabase.com/docs/guides/storage/buckets/fundamentals. Use authenticated user JWT reads under Storage RLS; do not switch evidence retrieval to public objects or service-role fallback.


## Implemented registry candidate

Migration `20261031224723_acquisition_contract_document_registry.sql` implements shared artifact/revocation contract targets, exact composite version identity, private retention purposes and authenticated register/revoke/state RPCs. This is local candidate migration 58; it has not run in production. Contract uploads intentionally fail the existing mail-only upload guard until shared admission and upload verification are implemented.

Eight focused SQL cases passed, including populated mail preservation, target constraints and two observed authorization-revocation lock waits. The full catalog/gateway run passed 58 migrations, 26 access checks, 95 workflows and 58 real local gateway checks. Registry registration/revocation/idempotency/RLS were exercised through actual PostgREST; this is not hosted Storage acceptance.

Typed contract registry reads now surround the bounded byte read. Current unverified state, exact contract/version/purpose, retention and policy identity must remain consistent; changed authority, revoked/expired documents, stale state or a different hash cannot yield a receipt. Shared registry transport and 582 related tests passed, followed by a focused store-forwarding check. These before/after byte-stream cases use synthetic HTTP streams; the combined actual registry-plus-Storage path still requires acceptance. No document scan/legal approval or review transition is persisted by the byte verifier.

Next implement the shared workspace upload admission for contract targets, exact upload completion/reconciliation, signed scanning and review bindings. Keep one aggregate workspace capacity and preserve every mail regression. Then add the document review controls beneath the existing draft step; verified metadata or bytes must never appear as a signed contract.


## Authenticated metadata API acceptance

The mounted version-scoped contract document API now supports registration, state read and revocation through the current user-JWT acquisition store. It accepts bounded expected bytes/hash/media/purpose, policy reference and exact provenance; actor/workspace/version overrides and approval assertions are rejected. Read projections include revoked/expired/policy-review states without claiming verified bytes or legal approval. Successful and handled failure responses are noncacheable; uncertain mutations preserve the same request/details for recovery. Upload, download, verify, approve and sign routes are not exposed.

681 related API/auth/evidence tests passed. The actual mounted API plus local gateway verified committed registration and revocation response loss, exact retries, two immutable audit events, current state, wrong-version/foreign/anonymous denial and upload unavailability. Full rehearsal: 58 migrations, 26 access probes, 95 workflows and 62 gateway checks; exact evidence in 2026-10-31-contract-document-api-gateway-result.json. Hosted Auth and actual registry-to-Storage-byte verification remain separate unproven gates. Continue shared upload admission, scanning/review bindings and evidence-backed contract transitions before presenting document completion as available in the app.
