# Contract document persistence implementation handoff

October 31, 2026. Local implementation checkpoint. Production uploads, legal review and signing remain unapproved; no runtime flag is enabled by this document.

## Current verified starting point

Read-only production inspection still reports migration ledger `20261023221455`, canonical `deals`, and RLS-enabled Storage tables. Candidate acquisition evidence/contract tables are absent. Storage object columns include archive/delete-marker/version flags; no Storage object policies were returned by the fresh catalog query. Exact metadata: `evidence/2026-10-31-contract-document-catalog.json`. Reinspect before writing the next migration; local candidate migrations are the intended additive predecessor, not the live state.

Migration 58 extends the existing `acquisition_evidence_artifacts` registry with mutually exclusive campaign and canonical contract-version targets. The mail interfaces remain campaign-bound. Retention policies and revocations support both targets; signer attestations, scan state and review bindings still require further contract-specific work. Do not supply a contract UUID in a campaign parameter or create a fake campaign to store contract documents.

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

`admit_contract_document_upload` rechecks current workspace/member/profile/session, activation, exact draft/version, creator, purpose, retention policy and revocation after waiting for capacity serialization. The returned decision grants no Storage or execution authority. Migration 59 grants no Storage authority. The follow-on Storage candidate described below adds exact-reservation dispatch; verification still rechecks authorization after writing.

Validation is tracked in CURRENT-STATUS.md and PROGRESS.md. The internal transport now has strict admission receipt parsing, shared process capacity, bounded source handling and authenticated reconciliation. Its synthetic tests do not establish Storage write authority. Storage dispatch and combined real-registry/RLS upload acceptance passed locally in migration 60. The separately disabled upload endpoint candidate is described below; scan/review binding and guided document UI remain next.

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

## Internal transport candidate

Contract admission rejects wrong target/version, stale timestamps, non-boolean authority flags, unexpected fields and invalid reservations before reading input. Both document types use the same four-slot process semaphore and 90-second outer deadline, in addition to database workspace limits. Cancellation during admission closes input and releases process capacity.

The shared upload engine retains one bounded in-memory source read, exact expected size/hash, conservative file-type precheck, a fresh registry read before one non-overwriting POST, and independent registry/bytes/registry reconciliation. Provider success bodies never prove stored bytes; uncertain writes preserve the artifact identity and exact file. Contract metadata observations remain unpersisted, unscanned and legally unapproved. Migration 60 supplies the Storage write guard and passed real-registry/RLS transport tests with synthetic object bytes. The next endpoint remains disabled by default; hosted Storage acceptance is separate.

## Storage authorization candidate (migration 60)

`20261031231025_acquisition_contract_storage_upload.sql` replaces only the existing private access helper. Mail target checks are preserved. Contract writes require the exact current draft/version, creator, workspace and active reservation for that artifact in the shared slots, plus existing MFA/session/role, activation, retention, revocation and private-bucket checks. Existing restrictive object policies retain no listing, signing, replacement/deletion or archived/versioned access. No new bucket or policy grants are added.

Focused SQL and combined bounded-transport cases use real registry/RLS with synthetic object bytes. Full-catalog workflow tests include fresh session/member revocation after admission, scoped preservation of a historical Storage sentinel, lost commit-reply recovery and activation/revocation changes across reads/writes. Hosted Storage behavior and production migration remain unapproved/unverified. Compensation: turn acquisition activation off and preserve all records/objects; do not remove retained evidence to roll back.

## Separately gated binary upload endpoint candidate

`POST /api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/{version}/documents/{artifact}/bytes?purpose=purchase_contract` accepts only the original registered binary stream. `ACQUISITION_CONTRACT_UPLOAD_ENABLED=true` is a separate default-closed gate; the mail upload flag cannot open it. The existing acquisition feature gate, current user JWT and database/Storage authorization also apply. No runtime environment setting was changed.

Mail and contract routes share the same lazy request-stream validation: one purpose, uncompressed application/octet-stream, no caller filename, bounded Content-Length and actual bytes up to 10 MiB. Admission runs before reading the body. Contract receipts validate exact artifact/workspace/contract/version/purpose, retained and fresh timestamps, expected verifier versions, strict booleans and no additional fields. A successful byte match reports stored_unverified, not_scanned, verification_persisted=false, legal_review_approved=false and execution_authorized=false.

`CONTRACT_DOCUMENT_UPLOAD_NOT_ACCEPTED` (409) means the file/current state was not accepted. `CONTRACT_DOCUMENT_UPLOAD_UNCONFIRMED` (503) preserves the same registered artifact and exact file for reconciliation. Capacity denial returns 429 and Retry-After; do not switch identity to evade that hold. No downloadable URL, preview, legal approval or signing action is returned. Endpoint and real-registry/RLS acceptance are recorded in CURRENT-STATUS.md; hosted provider acceptance remains pending.

## Guided document discovery candidate (migration 61)

`GET /api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/{version}/documents?purpose=purchase_contract` returns a bounded, ordered page of current metadata for the exact retained version and the latest currently reviewed retention-policy choice for that purpose, or null. The next_after cursor is the last returned artifact ID, with 1–50 rows per page. Missing policies are never fabricated. Discovery remains available during an acquisition pause so revoked/expired history can still be reviewed; all write paths recheck their own current authority.

The database RPC validates current MFA workspace role/session, actual canonical version and permitted document purpose. It returns no provenance text, private file path, download URL, verification or legal approval. Strict API validation rejects mixed versions/workspaces, duplicate or unordered rows, malformed cursors, stale states and injected availability. The separate upload_enabled value comes from server configuration only and is not contact, Storage or transaction authorization.

For the app, keep this list inside the saved contract draft context. Present document purpose, creation time, size and plain status, with detailed identifiers hidden from the primary flow. Preserve the exact pending registration/upload identity across reloads and block workspace/draft navigation during uncertain recovery. A stored file must remain visibly awaiting scan/review until those signed evidence bindings are implemented.


## Guided UI and internal scan checkpoints

The saved-contract step now includes document upload/discovery with exact pending recovery and parent navigation holds (58bbf32, local until CI publication gate). A definitive rejection of only the first registration attempt can release the hold; unknown or later rejected attempts retain their exact identity. Full frontend regression 607 passed, plus build/lint and synthetic visual/recovery QA.

Internal `scan_registered_contract_document` now uses the shared mail `_scan_registered_object` lifecycle and process capacity. Contract scope/version/purpose remain distinct; no campaign substitution is possible. Current registry checks surround bounded exact bytes and pinned local daemon observation. No detection means only an unpersisted scan observation; no preview, legal or signing authority. Full backend 3287 passed. Next extend signed attestation and persistence with exact contract/version target and shared byte-alias detection. Preserve existing mail signatures and immutable historical receipts. No migration or live scanner configuration is supplied by this checkpoint.


## Contract-specific signed observation format (internal candidate)

`tools/acquisition_contract_attestation.py` validates exact internal `scan_observed` output using shared ScanObservation fields and contract-specific target/version/purpose. Strict false verification/scan persistence, preview, legal and execution flags are required. A distinct ContractVerificationSigningKey requires an explicit nonempty frozen set of permitted contract document purposes, current workspace, scanner signature/version policy, 32-byte secret and at most 24-hour validity window. Existing mail signing key objects are rejected. No environment key lookup, provisioning or public signing route exists.

The HMAC-SHA256 message is `acquisition-contract-document-attestation-v1`, newline, then newline-separated request/workspace/contract/decimal-version/purpose/artifact/actor/session/key identifiers, newline, then the exact canonical observation JSON (sorted keys, compact separators, ASCII, no NaN). Output keys are p_id, p_workspace, p_contract, p_version (integer), p_purpose, p_artifact, p_actor, p_session, p_key, p_observation and p_signature. Preserve this exact request for retries; never regenerate it from a newer scan after an uncertain write.

The future database migration must independently verify this domain and exact ordered context, derive artifact target and current purpose/version, require separately reviewed contract-purpose key provisioning (no automatic upgrade of old mail keys), fresh current actor/session/role and registry/retention authority after lock waits, and persist immutable observations/audits with exact historical retry receipts. Detection holds must cover matching bytes across mail and contract aliases. Current signed requests have no mounted persistence RPC, journal dispatch or database acceptance and must not be presented as review evidence yet.

200 combined contract/mail scan, signing and byte-verification tests passed, including actual internal scan output -> contract signature, context changes, missing/foreign fields, stale or approving observations, expired/mismatched keys and mail-key rejection. Keys and daemon responses are synthetic. No production credentials, scanner, migration or policy were activated.

Read-only hosted metadata was refreshed after the signing checkpoint: migration ledger remains 20261023221455; shared artifact/verification and contract-version candidate tables remain absent. Evidence: evidence/2026-10-31-contract-attestation-catalog.json. Inspect local predecessor definitions, constraints, indexes, RLS and latest function overrides before creating the additive persistence migration. No hosted SQL mutation was performed.


## Candidate database persistence implemented (migration 62)

The database requirements above are now implemented by `20261031234409_acquisition_contract_observations.sql`, with separately reviewed private contract-purpose key scopes and an extension to the shared immutable observation ledger. Actual Python signatures were accepted by local PostgREST; exact concurrent retries converge, cross-tenant/version/session writes fail, and matching-byte detections block mail aliases. Seven focused SQL cases and the 62-migration rehearsal (119 workflows, 69 gateway checks) passed. This supersedes the earlier statement that no candidate persistence RPC exists.

Typed application transport, durable journal dispatch/recovery and current review bindings remain unimplemented. No public scan endpoint, signing key provisioning, scanner activation, hosted migration or legal approval is supplied. Preserve exact request bytes on uncertain writes and retain observations/audits when compensating by revoking reviewed key scopes.


## Typed transport and durable recovery candidate

`tools/acquisition_contract_persistence.py` and `AcquisitionStore` now provide exact-target, bounded, user-authorized persistence. The existing `EvidenceJournal` stores both strict mail and contract envelopes in the same private database with one capacity limit. `persist_journaled_contract_observation` requires the original user/session/contract/version/purpose, binds the original destination before dispatch, and reconciles exact historical requests through the database even after a locally confirmed receipt. No signing, identity renewal, automatic dispatch or present review authority comes from journal history.

Mail request/receipt types remain distinct. Mixed targets are rejected, original signed JSON text is preserved, and contract receipts must explicitly deny preview/legal/execution authority. Local process cancellation or uncertain HTTP/database/disk outcomes retain the original request. Hosting the persistent volume, actual scanner/key operations, current scan-state discovery and human-review bindings remain pending. Validation is recorded in CURRENT-STATUS.md.


## Current scan assessment candidate

`contract_document_scan_state` assesses the exact workspace/contract/version/purpose/artifact through the shared observation ledger. It does not trust a previously returned receipt as current authority. New `ContractDocumentScanState` validation and the store read use the existing bounded authenticated registry transport with a fixed RPC and a fresh checked_at deadline. Mixed targets, stale timestamps, ambiguous JSON, malformed status/observation combinations or any approving flags are rejected.

The current observation disappears when its signing key or reviewed contract purpose expires/revokes, or its original actor membership/profile/session is no longer valid. Retention/revocation status takes priority; matching-byte detection remains sticky across both mail and contract records. Read-only assessment works during an activation pause and creates no scan, audit or approval. The internal reader is not yet mounted in the browser API or rendered in the document list. Human document/title review bindings, approved terms and state transitions remain required.


Next app handoff: add authenticated `GET /api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/{version}/documents/{artifact}/scan-state?purpose=...`, with no-store responses and the same exact-target/freshness validation. Extend the existing `ContractDocuments.tsx` history rows rather than creating a separate document dashboard. Keep one clear document status, explain review-needed/quarantine states in plain language, and preserve pending upload recovery and parent navigation holds. A current no-detection observation must still say human review is pending. Do not expose a private preview, trigger scanning from this read, or add signing/approval buttons until the corresponding evidence-bound reviews exist. Include denied/stale/loading/error states and phone-width QA.


## Document-status interface candidate

The planned GET `.../documents/{artifact}/scan-state?purpose=...` is mounted with exact target/freshness validation and no-store responses/errors. The existing document history offers an on-demand check, with no parallel dashboard. Human review remains pending after scan completion. Detection/expired/revoked/review-needed states have plain labels. The UI hides prior successful state during retry/error and after 30 seconds; list context changes discard the old result. Pending registration/upload recovery is unchanged.

Synthetic fixture `?scanFixture=true` seeds an explicitly synthetic saved draft/document and returns artificial no-detection status for presentation checks. It uploads/scans no actual bytes and is not provider/scanner acceptance. Desktop/phone screenshots are retained; component tests cover detection, error and rendered expiry. Current gateway/CI status is in CURRENT-STATUS.md.

## October 31 — exact human contract reviews (local candidate 64)

Added immutable contract, title and assignment-basis reviews bound to the canonical contract version, exact retained artifact/hash and latest verification. Explicit reviewer policies are private, workspace-scoped and empty by default. Owner/admin MFA, active membership/session, approved reviewer authority, fresh evidence and bounded expiry are required. Historical retries preserve one decision and audit without returning current approval. Withdrawal remains available to the original reviewer after policy/evidence expiry or acquisition pause; cross-reviewer withdrawal is not implemented. Current-state reads recheck authority and shared matching-byte detection holds. No signing or transition authority is returned.

Validation completed: nine focused database tests passed in 46.607s. Full rehearsal exited 0: 64 candidate migrations, 26 access probes, 134 workflows and 76 actual local gateway checks. All 24 historical rows in 22 tables, 103 definitions and the Storage fixture were preserved. Evidence: `evidence/2026-10-31-contract-human-review-gateway-result.json`. An earlier contention test missed a buffered lock marker; its synchronization now emits a single marker, and the corrected focused suite passes. Authorization rules were not weakened.

This is database foundation only: typed human-review API, guided review interface, policy provisioning, immutable terms, persisted transitions and disposition remain unfinished. No production migration or activation. Compensation keeps history intact: revoke review-policy authority or pause acquisition; do not delete decisions/audits.

Publication: c3b91a7 remains remote; local interface commit 69dc0ef is unpublished. CI 41255050827 has four successes, one dependency-setup timeout and one still-live contention job. Isolated repair b92ba6b is committed in /tmp/wholesale-ci-repair-20261031, with workflow parsing and 28 shell syntax checks passing. Wait for the live predecessor to terminate before publishing the repair; require all six successor checks before feature publication.
