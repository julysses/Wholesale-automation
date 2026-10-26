# Acquisition automation — progress and resume checkpoint

Checkpoint date: October 26, 2026 (America/Chicago).
Status: implementation in progress on `codex/acquisition-foundation`; production remains unchanged.

## Implementation checkpoint — isolated durable provider receipts

- Previous turn was progress: `7c68ef8` hardened Facebook authentication/envelopes and passed backend regressions. Pulled that clean branch before this update. Applied Supabase skill; reviewed function security documentation, catalog queue columns/constraints/policies, source migration/index and Retell/monitoring consumers.
- Added CLI-generated `20261026153314_acquisition_provider_inbox.sql`, extending existing webhook_jobs rather than introducing a duplicate inbox. Private disabled-by-default integrations map provider accounts to one workspace; privileged configuration changes are audited and identities cannot be reassigned.
- Service-only acceptance requires enabled global/integration gates and an active workspace. Unique provider event identity, transaction locks and content hashes make concurrent retries idempotent and conflicting replays fail. Receipts retain the original raw bytes and canonical event payload. No browser-provided workspace routing is accepted.
- Acquisition source/status remain outside the legacy pending drain. Restrictive browser RLS and guarded raw service writes preserve receipts. Bounded retention purges expired bodies/answers while keeping identity/hashes and audit. No scheduler, subscription, processor, HTTP wiring or production change was introduced.
- Validation: **69 disposable PostgreSQL tests passed**, including four new inbox tests; **3 real API/calculator/database journeys passed** with the additional migration. SQL guards verified against actual roles and concurrent sessions. `git diff --check` passed. An initial Python compile invocation hit a sandbox cache-write restriction; syntax was verified with in-memory AST parsing and both database runners executed successfully.
- Documented routing, retention, compensation and unimplemented boundaries in PROVIDER-INBOX.md; updated entity mapping and migration test plan. Full production-schema/actual PostgREST acceptance and reviewed retention policy remain outstanding. Engineering retention default is not legal approval.

Next: dedicated acquisition claim/lease/completion and retry/credential reconciliation; then verified asynchronous Facebook HTTP acceptance with durable persistence before acknowledgment, Page configuration/token management, seller intake and attribution. Install a monitored retention runner before live acceptance. Existing inline Facebook and paused SMS paths remain unchanged. Goal active.

## Implementation checkpoint — Facebook webhook boundary

- Pulled `2fb4395` successfully after retrying sandbox DNS failure through approved Git network access. Inspected existing adapter, HTTP receiver, generic queue, campaign/entity mapping and receipt uniqueness.
- Hardened the reusable adapter against blank signing/verification credentials, malformed/non-ASCII signature headers, and empty challenges. Existing HTTP credential checks remain. Signature comparison uses the exact raw body; malformed signed event envelopes now return 400 before any processing rather than throwing or inventing a `None` lead identity.
- Added 25 offline boundary regressions; focused security suite **38 passed**, full backend **1,294 passed, 10 skipped, 368 existing warnings**. No provider calls, migrations, configuration or deployment changes.
- Durable ingestion is still pending: current Facebook handler processes inline; generic queue insertion returns false on storage failure and legacy callers can acknowledge anyway. Existing `webhook_jobs` has service-only RLS but no tenant/provider-event identity or lease. Existing native receipts have globally unique leadgen ID and unique lead ID; repeat inquiry semantics must preserve SMS receipt foreign keys. Do not route the new acquisition pipeline through the legacy drain until a separately isolated inbox/claim path exists.

Next: extend webhook_jobs with acquisition workspace/integration/event identity and immutable receipt controls after full constraint/policy inspection; isolate legacy drain, add atomic idempotent acceptance and lease/reconciliation, require persistence before acknowledgment. Then implement authorized Page routing, lead retrieval/credential alerts, canonical identity/intake and attribution. Current API version, subscription permissions and provider contract still require official-document verification before new integration deployment. Goal active; production and paused SMS unchanged.

## Implementation checkpoint — API/calculator/database workflow acceptance

- Pulled clean `6403a01`; prior turn implemented/tested/pushed operator underwriting and proposal entry (progress). Inspected current engine fixtures, API/store/worker boundaries and isolated database harness.
- Added a repeatable workflow harness that runs the real FastAPI router, schemas, scoped store, calculator and SQL/RLS/audit functions against the disposable database. Only the PostgREST HTTP hop is adapted to local SQL with explicit synthetic identities. No calculated output is fabricated. Offline runner clears secrets/dotenv and blocks Python networking; cluster is socket-only and destroyed after tests.
- Three journeys pass: sourced calculation through internal offer review with cross-tenant denial/idempotency; missing downside market data remains incomplete and cannot create an offer; a lost completion response reconciles the already-committed revision without another calculation write.
- The last journey identified/fixed contradictory API metadata: a confirmed final scenario no longer returns pending calculation status after a lost worker reply. The fresh user-authorized database read now reports the reconciled terminal outcome.
- Added a dedicated CI workflow job. Root collection inspection proved it was collecting standalone runner classes without their cluster setup; ordinary pytest now excludes only those two runner files, retains other backend/county tests, and runs under the offline boundary. Database suites retain dedicated jobs.
- Validation: **3 real-calculation/SQL API journeys passed**. Existing backend-only suite: **1,269 passed, 10 skipped**. Broader repository suite using the revised CI collection: **1,306 passed, 10 skipped, 6 subtests passed, 368 existing warnings**. `git diff --check` passes. Remote CI completion not yet claimed. Details/limits: WORKFLOW-ACCEPTANCE.md.

Next: actual PostgREST/auth and browser/database acceptance, remaining strategy persistence journeys and full-schema upgrade rehearsal; current-scenario/final-document controls; policy execution and durable Facebook intake before later channel activation. No production migration, deployment, configuration, provider or transaction changed. Goal active.

## Implementation checkpoint — underwriting entry and proposal creation

- Pulled clean `1fad9ca`; previous turn browser-tested review and pushed financial formatting (progress). Rechecked current input models, workspace lead listing and saved scenario/proposal API contracts.
- Added a paginated property/scenario workspace within the default-off review screen. Four strategy forms collect independent base/downside/upside assumptions with explicit source, basis, confidence and date; wholesale includes separate buyer economics. Blank remains missing, sourced zero is preserved, malformed values are blocked, and no market data is invented.
- Added preview, immutable save, pending-calculation resume and proposal creation against a selected saved revision. Stable IDs/exact payloads survive uncertain responses for explicit retries. Pending calculations never become calculated in the browser. A just-saved scenario is selected directly, independent of history pagination; server role/session/property/latest-revision checks remain authoritative.
- Extracted the scenario comparison into a shared component that displays missing inputs and appropriately formatted financial metrics for preview, saved scenario selection and review. Kept mutation controls separate from approval/delivery and left all activation controls unchanged.
- Updated the review-only browser fixture for the new read request; it does not simulate underwriting creation. New input-flow validation is through component tests, not a claim of browser or production-connected acceptance. Validation: **189 frontend tests passed across 46 files**, feature-enabled TypeScript/Vite build passed, and lint ratchet reported no new findings (147 existing). After the final direct-selection change, **9 focused tests and TypeScript compilation passed**. `git diff --check` passes. No backend/schema code changed in this checkpoint.

Next: browser input-flow and database-connected acceptance, current selection/approved document workflow, policy execution and shared intake/attribution foundation for Facebook. All later ordered channels remain in scope. No backend/schema/deployment/provider activation changed. Goal active.

## Implementation checkpoint — browser QA and financial display units

- Pulled clean `8e45d1a`; previous turn implemented/tested/pushed the default-off review screen (progress). Created a reusable localhost-only browser fixture that renders the actual component/styles and replaces only the API with synthetic in-memory data. No environment files, auth, Supabase, providers or real transactions are used.
- Exercised workspace selection, exact evidence, disabled incomplete approval, seven diligence notes/acknowledgment, synthetic decision confirmation, queue update and revocation availability in the in-app browser. Reviewed a 375px mobile viewport and restored the normal viewport. Browser error log was empty. Saved `evidence/2026-10-26-offer-review-browser.jpg`.
- Browser inspection found raw profit and ratio values. Added explicit engine-metric currency/percentage/coverage formatting and regression tests, preserving null versus zero and avoiding guessed units for unknown metrics. Verified corrected dollar and percentage values in the browser.
- Fixture was initially written beneath a duplicated frontend directory; moved it to the intended tests/browser path. Starting localhost was blocked by sandbox binding permissions, then ran under approved command escalation. Browser selector mismatch was resolved through the observed native accessibility control. These were tooling issues, not skipped acceptance checks.
- Validation: **183 frontend tests passed across 44 files**; feature-enabled TypeScript/Vite build passed (existing chunk/annotation warnings); lint ratchet reports no new findings (147 existing). `git diff --check` passes. No backend/schema/production configuration changes. This fixture does not prove real authentication, RLS, persistence or production integration.

Next: underwriting input/proposal creation interface, current scenario selection and final-document workflow; full-schema/database-connected acceptance, policy execution, durable Facebook ingestion and remaining ordered channels. Goal active.

## Implementation checkpoint — workspace offer-review screen

- Pulled clean `fb131f5`; previous turn implemented/tested/pushed current approval projections (progress). Inspected current app routing, sidebar, API session helper and frontend tests. Applied React best-practices skill for keyed components, parallel reads, accessibility and lazy loading.
- Added a default-off `VITE_ACQUISITION_ENABLED` route/navigation entry for `/acquisition-review`, inside existing authentication/approval/layout. Workspace-specific queue and detail show exact scenario/case, proposed amount/ceiling, current versus historical decision, blockers, canonical address, base/downside/upside MAO/metrics and expandable provenance/history.
- Added a minimal user-token lead summary endpoint: exact binding is authorized before returning address/city. Missing/mismatched property or analysis evidence prevents review recording. No contact export or client-selected property is introduced.
- Decisions require an explicit action/note/acknowledgment and seven diligence notes for approval. UI rechecks state before POST and uses the exact sequence. Double clicks are guarded; unknown outcomes retain UUID/payload for explicit retry. Workspace/account changes reset detail state, query keys include user/workspace, and drafts are not persisted locally.
- Validation: **182 frontend tests pass across 43 files**, including deliberate approval, revoked-action preflight, exact retry payload and workspace switching. **Full backend 1,269 passed, 10 skipped, 368 existing warnings.** TypeScript/Vite builds passed both default-off and feature-enabled configurations (existing large-chunk and dependency annotation warnings). Dependencies installed with `npm ci --ignore-scripts`; audit reported zero vulnerabilities. One initial test command used the repository root instead of frontend and was corrected; no test failure was hidden. Lint ratchet passes with **no new findings** (147 existing findings remain). `git diff --check` passes.

Next: local browser visual QA and full database-connected UI acceptance; intake/underwriting/proposal entry and final document approval; policy execution, Facebook intake and ordered later channels. No production migration, deployment, configuration, provider, campaign, mail or binding transaction changed. Goal active.

## Implementation checkpoint — current approval state and review queue

- Pulled clean `1fbbd72`; prior turn implemented/tested/pushed proposal/amount-review lifecycle (progress). Rechecked current membership timestamp semantics, offer-event schema and role helpers before adding forward-only read projections.
- Added `20261026041845_acquisition_offer_review_state.sql`: current state separates historical approval from current internal amount review. Newer or incomplete underwriting, disabled acquisition activation and changed approver authority invalidate the current indicator without changing history. Membership re-enrollment does not resurrect old approval.
- Added a bounded workspace review queue, exact latest event/sequence and role-appropriate review actions. User-token API routes expose state and queue; no service-role fallback or approval mutation occurs during reads. Every response unconditionally denies transmission and supplies no execution authorization. Mutation RPCs still enforce fresh checks independently of the displayed actions.
- Documented point-in-time semantics, UUID pagination, revocation availability and remaining profile-history/document/expiry rules. The internal amount indicator is not a delivery gate; the frontend and final written-offer approval remain unfinished.
- Validation: **65 disposable PostgreSQL tests passed; full offline backend 1,268 passed, 10 skipped, 368 existing deprecation warnings.** `git diff --check` passes. No production migration or runtime/provider changes.

Next: build the workspace review screen, connect exact proposal/scenario evidence and deliberate human decisions, then current-scenario selection and final-document workflow. Continue full-schema upgrade acceptance, policy execution, Facebook intake and all remaining ordered phases. Goal active.

## Implementation checkpoint — proposal and amount-review lifecycle

- Pulled clean `fdd426e`; prior turn implemented/tested/pushed immutable scenario persistence (progress). Inspected the current catalog columns, FKs, RLS/ACLs, indexes, reportable view and migration history for `offer_recommendations` before generating the additive migration with Supabase CLI.
- Extended the existing recommendations with workspace, exact scenario/case, proposer and rationale. Added immutable review events with sequence checks, stable IDs, role-enforced transitions and audit. Proposals require the latest calculated property-bound scenario and an amount at or below its computed case ceiling. No current lead estimate/offer field changes.
- Owners/admins may approve an internal amount after documenting title, liens, occupancy, valuation, repairs, financing and downside review. Operators can propose/withdraw; callers/agencies cannot approve. New underwriting blocks stale approvals. Concurrent decisions serialize against both the offer and scenario reservation. Activation blocks new approvals but leaves revocation/withdrawal available.
- Added user-token proposal/review/history APIs, bounded pagination and explicit 409 refresh responses for concurrent state changes. No actor override, sent state or transmission route. Internal amount approval does not approve a final legal document or authorize outreach. See OFFER-REVIEW.md for exact remaining document/approval/expiration/identity gates.
- Extended isolation to legacy recommendations linked through analysis as well as lead; mixed workspace parents are denied. Raw service-role insert/update/delete/truncate cannot change scoped history. Existing unbound behavior is preserved.
- Initial SQL fixture run failed because the newly included legacy recommendations referenced the omitted qualification/transcript chain. Scoped fixture now explicitly omits that unrelated FK, while retaining the analysis and lead FKs; production migration does not remove any FK. Initial offer lifecycle cases subsequently passed. Final validation: **62 disposable PostgreSQL tests pass; full offline backend 1,267 passed, 10 skipped, 368 existing deprecation warnings.** `git diff --check` passes.

Next: current scenario selection, effective approval freshness/invalidation, approved-template/document workflow and review dashboard; source/property uncertainty evidence; policy execution and durable Facebook capture, followed by remaining ordered channels. No production schema, runtime flags, provider, campaign, sender, mail or transaction changed. Goal active.

## Implementation checkpoint — immutable underwriting scenario history

- Continued from pushed `32f0401`; pulled again before finalizing (already current). Inspected the existing analysis table, latest legacy sync function, manual-save RPC and tenant boundaries before generating the additive migration with Supabase CLI.
- Extended `deal_analyses` through `20261026040321_acquisition_analysis_versions.sql`. User-scoped reservations preserve canonical lead/property binding, immutable inputs, original actor/session, hash, calculation version and ordered revisions. Exact retries are idempotent; changed inputs under the same ID conflict. Concurrent requests allocate distinct revisions.
- Added dedicated server calculation read/finalize RPCs and `tools/acquisition_calculator.py`. The worker reads the stored input snapshot, computes with the tested four-strategy engine, and records outputs once. Caller-supplied outputs and raw service writes are rejected. Worker operations recheck original session, profile, role, workspace and activation. User-visible results are re-read through user RLS. Worker trust and dedicated service credential limits are documented in UNDERWRITING-V1.md.
- Added scenario save/history APIs. Disabled or unavailable calculator leaves an explicit pending record; an unknown result requires retry of the same ID. No generic service-key fallback, provider calls, background scheduling or offer approval. Invalid stored schemas get a terminal rejection, while unknown engine versions remain held.
- Preserved legacy synchronization for unbound analyses; workspace-bound analyses never change lead ARV/repairs/MAO. Final review found and closed an old-record reassignment bypass by checking both old and new lead bindings before legacy writes. Completed history and audit are immutable.
- Validation: **55 focused Python tests passed; full offline backend 1,265 passed, 10 skipped, 368 existing deprecation warnings.** Final focused disposable PostgreSQL suite after the reassignment fix: **56 passed**. `git diff --check` passes. SQL uses synthetic result payloads to test persistence boundaries; Python independently tests calculation/orchestration. Full production-schema and PostgREST end-to-end acceptance remain open.

Next: scenario selection/approval and offer lifecycle; property/market uncertainty evidence and dashboard; policy/execute controls and owner assertion invalidation; durable Facebook capture and sequential later channels. No production migration, environment flag, credential, sender, campaign, mail or binding transaction changed. Goal active.

## Implementation checkpoint — shared underwriting calculations

- Pulled clean `7bc438f`; prior turn implemented/tested/pushed legacy transport fences (progress). Inspected existing manual-analysis API, legacy ratio-based analyzer, `deal_analyses` columns/constraints and the schema-mapping persistence plan. Existing workflows remain unchanged.
- Added explicit provenance-bearing Decimal input schemas and `acquisition-underwriting-v1` calculation engine for flip, rental, development and wholesale. Explicit base/downside/upside cases share one strategy. Missing/null required data produces incomplete outputs, not zero; invalid numbers/rates and unsupported fields are rejected. Estimated/source-reported input never becomes independently verified property fact.
- Costs separate acquisition closing/liens, repair or construction categories, contingency, pre-exit/stabilization holding, simple financing interest, points/fees and selling costs. Debt principal is never double-counted as an expense. Rental NOI, reserves, debt service, cash flow and three price ceilings are separated. Assignment gross/net proceeds require independently supported end buyer economics.
- Added conservative offer-ceiling rounding, negative-MAO visibility, unknown/zero distinction, nonpositive-equity holds, case-label ordering checks and explicit fixed-debt/peak-funding limits. No market data is fetched or invented. Initial development test expectation had an arithmetic error (costs sum to 670,000, not 770,000); independently summed the categories and corrected expected MAO/profit.
- Added operator-only scoped preview endpoint using existing workspace binding RLS. It reads canonical property ID, rejects inaccessible leads and writes no analysis/MAO/offer. Returns `persisted=false`, nonbinding status and approval requirement. See `UNDERWRITING-V1.md` for precise formulas and limits.
- Validation: **48 focused underwriting/API tests passed** before adding the final case-order check. **Full offline backend: 1,259 passed, 10 environment-dependent tests skipped, 368 existing deprecation warnings.** `git diff --check` passes. No SQL migration, production configuration, provider or transaction changed.

Next: persist versioned cases by extending existing deal_analyses and protecting its legacy lead-sync trigger; add scenario/offer review lifecycle. Continue policy execution, owner assertion invalidation, durable Facebook intake/attribution, and all later ordered phases. Pure preview is not claimed as completed UW persistence or a production release. Goal active.

## Implementation checkpoint — legacy provider execution fence

- Pulled clean `d8d266a`; previous turn implemented/tested/pushed structured permission evidence (progress). Traced actual provider calls separately from LLM `messages.create` calls; no LLM generation methods were treated as outreach.
- Added `tools/acquisition_transport.py` and guards in legacy SMS, email, Retell voice/native SMS/app Twilio, Air AI and Vapi transport methods. With `ACQUISITION_ENABLED=true`, these paths require the future acquisition executor and cannot send under existing legacy clearance alone. No payload boolean, cached decision, recipient allowlist or existing live flag bypasses the fence. Feature flag is rechecked per invocation; existing clients cannot cache permission.
- Guarded native SMS enrollment/draining, app worker readiness/direct submit, carrier reply redirect and voice initiation/batch advancement before database claims or provider requests. Read-only reconciliation remains available. Pending-policy holds are excluded from Air/Vapi retry decorators. Existing paused jobs are not replayed or mutated by the hold paths tested.
- Added equivalent early rejection in the legacy Facebook Edge Function: acquisition-mode handler returns 409 before parsing/DB writes, and its direct SMS function returns false. This is a separate runtime: its deployment/flag must be coordinated or the legacy function retired before activation. No Edge Function deployed.
- The fence holds all legacy email, including internal alerts, during acquisition mode because the shared adapter lacks a trusted purpose distinction. Separate internal operational notifications and implement scoped approved execution before activation; do not whitelist based on a caller-supplied purpose. Flag-off legacy behavior is preserved.
- Validation: **10 targeted transport tests pass**, covering public/private methods, zero DB/provider access and no retry on the new hold. **One Deno runtime test passes** for the actual legacy Edge source with external imports replaced by failing spies and no network permission. Added that test to CI. **Full offline backend: 1,233 passed, 10 environment-dependent tests skipped, 368 deprecation warnings.** After adding the call-readiness display hold, **64 focused call/transport tests pass**, including readiness false even when legacy consent/live settings are otherwise ready. `git diff --check` passes.

**Not a final sender implementation:** no ALLOW execution path, transactionally consumed authorization, approved legal policy or automatic provider activation has been introduced. The fence prevents known legacy bypasses while those pieces are built; it is not proof of a complete production cutover or every externally configured sender. Current SQL/operator tooling and deployed runtime flags still require coordinated acceptance. Production remains unchanged.

Next: implement policy review/versioning and fresh execution authorizations; split internal alerts; complete owner assertion invalidation and effective evidence/expiry handling. Then durable Facebook intake and remaining ordered channels. Goal active.

## Implementation checkpoint — structured permission evidence and revocation

- Pulled clean branch at `9d8558b`; previous turn implemented/tested/pushed owner associations (progress). Inspected existing website receipt capture, native checkbox parser, SMS consent checks and native immutable-receipt migration. Source receipts and held SMS recovery records remain unchanged.
- Added CLI-generated `20261026033554_acquisition_permission_evidence.sql`. Server-side imports reference an existing receipt on the same bound lead and exact normalized endpoint. Structured records preserve channel, intended property-inquiry scope, source/form identifiers, raw consent evidence, affirmative/declined/unknown selection, disclosure text/hash version, source timestamp and import actor/time. There is no client-provided acceptance, approval or expiry override.
- Website SMS imports require matching disclosure hash/form metadata. Native SMS and AI-call imports independently reconcile the saved selection against exactly one matching raw checkbox and its disclosure. Missing/inconsistent evidence, ambiguous timestamps and future dates never become affirmative evidence. Valid affirmative selection remains **unreviewed**, never outreach permission.
- Expiry remains explicitly undetermined (`expires_at=null`, `expiry_basis=not_reviewed`), not unlimited consent. General policy review, expiry rules, scope interpretation and additional channels remain to be implemented and approved. The pending eligibility evaluator still has no ALLOW path.
- Added immutable revocations and a security-invoker status view. Assigned callers with MFA can revoke an accessible permission; the transaction also writes the matching channel suppression and audit. Revocation remains available while enrollment is disabled. Idempotent retries preserve evidence; no unsuppression or deletion path exists.
- Added import, bounded status-list and revocation API routes. Raw evidence/status rows stay operator-only. Revoked imports report their current revoked flag without modifying original selection. Test fixtures reconstruct receipt shapes; selected tests mutate only isolated synthetic receipts to exercise inconsistent evidence, not production immutability.
- Validation: **24 acquisition API tests pass**. Final expanded suite: **51 disposable PostgreSQL tests pass**, including duplicate/future evidence and atomic rollback on revocation/suppression identity conflict. `git diff --check` passes. No production migration, sender, provider, campaign or schedule changed.

Next: policy review/version model and effective permission selection/expiry; explicit owner-assertion invalidation; execution-time guards on all adapters. Then complete durable Facebook capture, intake/attribution and sequential remaining phases. Existing source adapters cover website SMS and native SMS/AI voice only; other permission sources/channels and full-schema upgrade rehearsal remain open. Goal active.

## Implementation checkpoint — explicit owner associations

- Pulled clean branch at `a8503a2`; previous turn implemented/tested/pushed pending-policy eligibility (progress). Rechecked live catalog evidence: county properties contain parcel/address identity but no owner name; CRM leads hold owner first/last name. No existing owner entity is duplicated.
- Added CLI-generated `20261026033010_acquisition_owner_relationships.sql`: workspace owner records with immutable CRM source-name snapshots, explicit owner/property/lead assertions and owner/contact assertions. Composite workspace FKs preserve canonical property identities. All tables require operator membership for reads, deny raw application writes and preserve append-only audit/history.
- Creation derives names server-side from a bound lead, rejects incomplete names, and uses supplied UUID for retry identity. Same names across leads do not auto-merge. Owner/admin review can associate one owner to multiple bound leads/properties; callers/agencies cannot create or associate owners. A missing canonical property remains null, never a fabricated property.
- Contact association requires an existing observation on the relationship's exact lead, not merely a matching phone elsewhere. Associations preserve review notes and observation IDs. Owner identities, title/authority and contact relationships remain unverified; no consent or eligibility is inferred. Separate asserted co-owner/representative records are supported, without automatic identity resolution.
- Added create/list/association API routes with bounded owner pagination and strict request schemas. Client-supplied property IDs, verified status and actor identity cannot override server derivation. Enrollment activation gates all new owner/association writes.
- Validation: **22 acquisition API tests pass**. **44 disposable PostgreSQL tests pass**, including owner retry/source preservation, same-name separation, multi-property links, matching-lead contact evidence, role isolation and activation gating. `git diff --check` passes. No production migration, data correction, provider call or outreach occurred.

Next: add evidence-backed verification and correction/revocation of owner assertions, structured per-channel permission/revocation evidence and policy review. Finish execution-time sender guards and durable Facebook intake before channel activation. Existing unverified assertions are not legal ownership evidence. Full PRD goal stays active.

## Implementation checkpoint — pending-policy eligibility and suppressions

- Pulled clean `026fdf6`; previous turn implemented/tested/pushed contact crosswalk (progress). Inspected latest legacy DNC and reviewed SMS resubscription functions before adding separate acquisition evaluation.
- Added CLI-generated `20261026032519_acquisition_eligibility_ledger.sql`: immutable channel-specific suppression records, immutable decision inputs/evaluated facts/results, workspace FK/RLS, live membership and explicit caller-assignment checks, generic cross-identity restriction results and existing audit integration.
- Added exact PRD route `POST /internal/outreach/eligibility/evaluate` using caller JWT plus public key. No client-supplied decision/policy/actor identity accepted. Each evaluation creates a fresh decision; no cached decision is an execution token. Pending policy always returns REVIEW or BLOCK, null expiry and empty permitted actions. SQL constraints prohibit ALLOW at this implementation stage.
- Suppression endpoint supports idempotent request IDs and assigned callers with MFA. Opt-out capture remains possible when enrollment activation is disabled. Suppressions cannot be deleted/replaced through application roles; no unsuppression flow is introduced.
- Acquisition checks compare matching normalized endpoints across workspaces privately, plus legacy lead DNC, dnc_registry, email suppressions, current listed skip-trace contacts and retained listed observations. Returned results contain no other workspace records/identifiers. Existing SMS exception functions and production provider paths are unchanged. Pending acquisition policy conservatively retains restrictions even where a legacy SMS-only review exists; no exception is extended to other channels.
- Validation: **39 real PostgreSQL tests pass** including cross-workspace/channel suppression, audit immutability, fresh decisions, caller MFA/assignment/revocation, source-retention DNC preservation and legacy formatted numbers. **83 focused HTTP/auth/identity tests passed** before adding an extra real-app internal-route boundary check; **full offline backend: 1,219 passed, 10 environment-dependent local-journey tests skipped, 367 existing deprecation warnings**. `git diff --check` passes. No production effect.

**Remaining enforcement work:** this is a persisted fail-closed evaluator, not finished legal policy or integration into every legacy sender. Permission/revocation evidence, calling hours/time zone, approved exceptions, workspace campaign resolution, address/direct-mail endpoints and execution-time transaction guards remain open. A supplied campaign adds CAMPAIGN_SCOPE_NOT_VERIFIED and never permits contact. Provider activation remains prohibited. Owner evidence relationships, workspace-aware legacy writes and durable Facebook ingestion also remain ahead.

Next: owner/property and permission evidence associations, policy version/review model, then fresh execution guards at every outreach adapter. Continue all PRD phases; goal remains active.

## Implementation checkpoint — canonical contact crosswalk

- Pulled clean branch at `2a42ee1`; previous goal turn implemented, tested and pushed the database activation guard (progress).
- Re-inspected catalog and source definitions for `wholesale_ingest.contacts`, `dnc_registry`, email suppressions and existing normalization guards. Existing skip-trace contacts combine phone/email and have expiring retention, so the new typed endpoint/observation crosswalk preserves source IDs and evidence without replacing or modifying provider storage.
- Added CLI-generated `20261026032050_acquisition_contact_crosswalk.sql`: workspace-local normalized phone/email endpoints, immutable source observations, composite workspace FKs, operator-only RLS, audited import RPC, activation checks and concurrent retry deduplication. Imports select canonical lead or skip-trace fields server-side. The API does not accept supplied normalized values, verification or consent claims.
- Phone parsing accepts explicit international codes and unambiguous US local formats, rejects letters/extensions instead of silently changing the number. Email normalization preserves the original in evidence. All imported endpoints remain **unverified**; expired observations preserve expiry and do not become current contact authorization.
- Same number on different leads shares only an endpoint inside a workspace, never an owner/property identity. Different workspaces get different endpoint IDs. Changed source values append history. Skip-trace retention can delete the source while provenance remains.
- Initial SQL tests found a variable qualification issue in the crosswalk lookup; renamed local variables and reran successfully. API tests: **18 passed**. Final expanded disposable PostgreSQL suite: **33 passed**, including cross-workspace endpoint separation and changed-source history. `git diff --check` passes.
- No production migrations, backfill, provider calls, schedules or outreach changed. Owner identity relationships, structured permission/revocation, suppression evaluation, general eligibility, contact verification and approved evidence-retention/redaction procedures remain outstanding; this slice does not satisfy all of MIG-003 by itself.

Next: implement owner/property evidence associations and per-channel permission/suppression/decision ledgers on these endpoints; preserve existing DNC semantics while keeping unapproved legal policy at REVIEW. Continue workspace-aware writes and durable Facebook ingestion, then subsequent ordered phases. Goal remains active.

## Implementation checkpoint — database activation gate

- Pulled `b6b9c43`; previous goal turn verified the completed push (progress evidence).
- Added CLI-generated `20261026031751_acquisition_activation_gate.sql`. Installation starts disabled. Workspace creation, membership enrollment/reactivation, lead binding and assignment require a private database activation record. Neither authenticated nor service-role clients can change it, including through direct PostgREST access.
- Activation requires a nonempty approval reference, exact application Git revision and verification timestamp. Database administration records transitions in a private append-only event table. These fields document operator attestation; they do not automatically verify a deployed application or supply approval.
- Activation checks hold a shared row lock until transaction end; disabling serializes against in-flight gated changes. Membership revocation and workspace suspension remain available. Existing scoped data and sticky restrictions persist when disabled; this is an enrollment/binding cutover guard, not an outreach authorization or universal runtime kill switch.
- SQL testing initially caught an absent `status` field on workspace_leads in the shared trigger; corrected using shape-independent JSON extraction. The membership RPC uses an upsert, so revoked states must also pass its INSERT trigger; that case was corrected and verified. Final validation: **27 real PostgreSQL tests and 17 offline acquisition API tests pass**; `git diff --check` passes.
- Production activation remains prohibited pending complete legacy functional replacements, full upgrade acceptance and explicit approval. No production migration or setting changed.

Next: canonical contacts/evidence and immutable channel eligibility, workspace-aware writes, then durable Facebook ingestion. The complete PRD goal remains active.

## Implementation checkpoint — request identity and related records

- Pulled clean branch at `ae45d2c`. Previous goal turn was progress (account containment and canonical binding committed, pushed and tested).
- Added ASGI request-local database identity when `ACQUISITION_ENABLED=true`. Protected API/internal/legacy requests use the caller JWT plus public key, including sync threadpool handlers. Missing, malformed or duplicate Authorization headers never select service-role credentials. Context resets after completion/error and parallel requests cannot borrow another token.
- Centralized buyer and webhook client factories through the same identity boundary; raw monitoring HTTP now follows protected request identity. Public form submissions, read-only public availability/config and signed provider/worker routes retain their validated server workflows. Startup settings loading remains server-owned.
- Protected cached and newly created SQLite CRM stores from scoped requests; old local-CRM HTTP workflows return 409 in scoped mode rather than bypassing RLS. With the feature flag off, legacy behavior remains unchanged.
- Added CLI-generated `20261026030633_acquisition_related_record_isolation.sql`. Existing UUID lead/deal/property-linked tables derive scope from canonical bindings. Raw authenticated writes to bound child records are denied; unrelated workspace reads and mixed-workspace parent combinations are denied. Bound county property-to-lead identity cannot drift.
- Validation: **25 real PostgreSQL tests pass**. Expanded fixture covers deals, buyers/import references, deal matches and county aliases. Initial fixture failures (missing buyer_import_log and required buyer last_name) were corrected; final suite passes. **Full offline backend: 1,214 passed, 10 skipped, 367 existing deprecation warnings.** Identity-specific suite: 25 passed. Real installed SDK was inspected locally and confirmed to retain the user Authorization header and public apikey. `git diff --check` passes.
- Commands: `python3 scripts/test_acquisition_workspace.py`; existing secret-free offline runner plus prior installed Python runtime, `-m pytest tests -q`. The 10 skipped local-journey cases require their separate database harness and are not claimed as passed. No production database, flag, provider, schedule or migration was changed.

**Cutover remains gated:** security is enforced in acquisition mode, but several old service-only RPCs will correctly reject user credentials until replaced/adapted. Local SQLite workflows are intentionally unavailable in scoped mode. Do not enable the feature or bind production records until functional replacements and a coordinated database/application activation gate are complete. Campaign/buyer ownership, orphan/JSON-linked historical evidence and full-schema upgrade acceptance also remain open. This is not a claim that MIG-002 or all legacy compatibility is complete.

Next: implement canonical contacts and immutable permissions/eligibility, plus workspace-aware write RPCs for acquisition workflows; add coordinated activation guards so direct PostgREST RPCs cannot create scoped production data before the matching application controls are approved. Continue toward durable Facebook ingestion and later sequential phases.

## Implementation checkpoint — acquisition account and lead boundaries

- Pulled `codex/acquisition-foundation` at `0442725`; worktree was clean. Previous goal turn is classified as progress (committed/pushed foundation and verified tests), not a wait or blocker.
- Added CLI-generated migration `20261026025259_acquisition_legacy_access_boundary.sql`: sticky acquisition-only profile flag; restrictive shared-table policies; a workspace-to-canonical-lead/property binding; audited binding/assignment functions; bounded assigned-lead projection. No duplicate lead/property data or automatic ownership backfill.
- Non-owner membership enrollment sets acquisition_only; revocation never restores shared legacy access. Existing non-owner memberships are covered when upgrading. Platform admin identities cannot be enrolled as limited caller/agency accounts. Existing account approval remains required.
- Legacy API authentication reads the optional new profile field compatibly with the prior schema and denies acquisition-only identities outside acquisition routes/the explicit eligibility endpoint. Internal routes now also require authentication. Raw scoped-lead mutation is denied to authenticated clients; mutations go through reviewed RPCs.
- Binding requires both a legacy platform administrator and workspace owner. County property association must already match the selected canonical lead. One lead/property cannot be adopted into two workspaces. Assignment requires a current member of the same workspace. Caller/agency queue projection requires MFA and explicit lead assignment, exposes no contact numbers, and caps pages at 50.
- Validation: **22 disposable PostgreSQL tests pass**, including preserved canonical property/lead data, same-phone nonmerging, preexisting membership upgrade, cross-workspace/raw-write denial, sticky revocation and assigned caller access. **121 targeted backend tests pass**, with 24 preexisting datetime warnings. `git diff --check` passes. Same isolated commands/runtime as the prior checkpoint; no provider connections or production writes.

**Security gate at this earlier checkpoint:** acquisition-only identities were contained but legacy service-role handlers still bypassed RLS. The newer checkpoint above adds request identity and derived parent scope; functional write replacements and coordinated activation remain required. No production account was enrolled or lead bound.

Next: finish legacy service-path isolation, then add canonical contact/evidence links, immutable per-channel permission and eligibility decisions, and durable Facebook receipts/processing. Full production-shaped upgrade rehearsal and later phase implementation remain open. Goal stays active.

## Implementation checkpoint — workspace foundation

- Refreshed Vercel production identity: still `c8673c170368bc8c44974fd304fac5af3fcf6e8c` / `dpl_3VmD6PS8eWxGYPh5qzVCZ9ouWW5d`.
- Created `codex/acquisition-foundation` from that exact deployed commit, preserving the complete production tree. Carried only the acquisition planning documents from `3fe1e9b`; no older application tree merged.
- Added `20261026024157_acquisition_workspace_foundation.sql` with the Supabase CLI. Additive workspaces/memberships, approved-profile and live-session checks, caller/agency MFA, owner/admin administration, last-owner protection, RLS and scoped immutable events in existing audit_logs. No legacy records auto-assigned.
- Added disabled-by-default `/api/acquisition/workspaces` and membership endpoints. User JWT and public Supabase key are forwarded to PostgREST; no service-role fallback. RPC authorization lives in private schema; public wrappers are security invoker. Input validation rejects supplied actor identity.
- Added a disposable Unix-socket-only PostgreSQL runner (no TCP, inherited secrets, cron/net extensions or provider SDKs). Reconstructs exact inspected column/constraint shapes for touched legacy profiles/audit dependencies, uses synthetic users/sessions and preserves legacy audit sentinels. It is a focused upgrade test, not a complete 103-table production restore.
- Added CI execution of the PostgreSQL foundation suite and disabled automatic Vercel deployments for this implementation branch.
- Validation: **15 real PostgreSQL tests pass**, including parallel creation and concurrent owner removal; **111 targeted backend tests pass** (14 acquisition HTTP cases plus existing auth/Facebook/Retell protections). Existing tests report 24 datetime deprecation warnings. `git diff --check` passes.
- Test commands: `python3 scripts/test_acquisition_workspace.py`; existing offline runner with the previously installed Python runtime at `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app/.venv/bin/python` against `tests/test_acquisition_api.py`, `test_api_auth.py`, `test_facebook_consent.py`, `test_facebook_request_security.py`, `test_facebook_sms_handoff.py`, `test_facebook_receipt_race.py`, `test_retell_webhook_security.py`. External runtime was used read-only; no old checkout changed.
- Sandbox shared-memory restriction required approval for the disposable PostgreSQL runner; it completed and destroyed its own test cluster.

**Not complete at this earlier checkpoint:** existing CRM/county tables and old service-role endpoints still use legacy shared access. The newer checkpoint above adds caller containment/bindings but retains the service-role bridge gate. Do not enable acquisition until all boundaries and full upgrade acceptance pass. No production migration, feature flag, provider configuration or schedule changed.

Next implementation slice: add workspace-bound lead/property/contact relationships and server-side authorization for legacy-resource bridges; preserve county property IDs and existing receipts. Then implement immutable channel permission/eligibility records and durable Facebook inbox. Keep the goal active through remaining PRD slices and acceptance gates.

## Latest checkpoint — live baseline and schema inventory

- Pulled planning branch before work; origin was up to date at `605f117`.
- Verified live Supabase project `dvzhzlipbwzzcliujzyz`; queried metadata only in READ ONLY transactions.
- Vercel hostname lookup returned production deployment `dpl_3VmD6PS8eWxGYPh5qzVCZ9ouWW5d`, READY, SHA `c8673c170368bc8c44974fd304fac5af3fcf6e8c`. Fetched this exact published commit for read-only inspection. Alias response omission and effective Vercel runtime flags/cron remain explicitly unverified.
- Captured 103 application tables, 17 views, 1,638 columns, 407 constraints, 248 indexes, 127 policies, 28 triggers, 122 function signatures/security settings and 95 live ledger entries. See `evidence/2026-10-25-catalog.json`; no business rows or secrets exported. This metadata snapshot is not a backup.
- Both private Retell schedulers are disabled and both Retell cron jobs inactive. Retention/monitor cron jobs remain active. No provider/worker was invoked.
- Confirmed a critical design gap: current application is shared approved-user access, with no workspace/tenant/organization ID columns in public/private/wholesale_ingest. Membership tenancy must be introduced and tested; existing development_workspaces is not an organization membership model.
- Confirmed existing county properties/contacts, campaign stores, native and website receipts, suppressions, analyses, recommendations, deals and buyers. Mapped all 16 PRD logical entities to extensions or justified additions in `SCHEMA-MAPPING.md`.
- Confirmed Facebook signature/receipt protections but synchronous inline processing; generic webhook_jobs lacks provider-event uniqueness. Added migration dependencies, compensation procedures and a disposable acceptance matrix in `MIGRATION-AND-TEST-PLAN.md`.
- Compared source/ledger: deployed source has 107 migration files; this planning base has 49, with 58 production files missing. Three live ledger names lack same-name production files. Comparison is not SQL-body equivalence. Do not release this older application tree or replay historical migrations.
- Validation performed: metadata/entity coverage and evidence consistency checks; `git diff --check`. Runtime, migration, RLS execution and live channel tests have not run.

This inventory checkpoint is historical; the implementation checkpoint above supersedes its next action. Production migration and activation retain separate approval gates.

## Verified this session

- Original workspace was empty and not a Git repository.
- Located existing WholesaleOS checkouts and verified their origin: `https://github.com/julysses/Wholesale-automation.git`.
- Cloned origin into this workspace's `app/` directory and ran `git pull --ff-only`: already up to date.
- Clone default branch: `claude/ai-wholesaling-agency-KkDF1`.
- Planning base: `ad70c7c29d618efe3aad848a386ca1779f0e7b8f` — Handle transient availability failures and preserve current production release.
- Created documentation branch: `codex/acquisition-prd-v1-plan`.
- No repository AGENTS.md was found by file inventory. User-supplied instructions govern: Codex pulls/pushes updates; GPT Work maintains a resumable planning/progress file.
- Captured all PRD requirement groups, logical entities, ordered activation gates and acceptance expectations in `IMPLEMENTATION-PLAN.md`.

## Checklist

- [x] Locate source repository and pull current default branch.
- [x] Save implementation plan and durable progress record.
- [ ] Verify deployed production code/schema and paused operations against current evidence.
- [x] Identify deployed revision, read live catalog and database scheduler state; effective platform/provider controls still pending.
- [x] Inventory existing schema, migration history, RLS, roles and equivalent entities.
- [x] Complete `SCHEMA-MAPPING.md` before writing SQL.
- [x] Document forward-only migration sequence, compensation and planned disposable tests.
- [x] Start isolated implementation branch from deployed production revision.
- [x] Implement/test workspace membership, administration API and scoped audit foundation.
- [x] Implement/test acquisition-only legacy-access containment, canonical lead/property binding and assigned-lead projection.
- [x] Route protected acquisition-mode requests through user JWT/RLS and isolate UUID lead/deal/property-linked records.
- [ ] Scope legacy service-role handlers and propagate workspace ownership to related records.
- [ ] Build/test shared foundation on a disposable database.
- [ ] Implement and pass Facebook acceptance with approved test leads.
- [ ] Obtain any required production migration/activation approvals.
- [ ] Pass inbound calling/mail gate.
- [ ] Pass portal/proposed-batch gate.
- [ ] Pass human-caller gate.
- [ ] Pass agency controlled-pilot gate.

## Repository context — not production verification

Earlier local checkouts have different heads:

- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/app`: `codex/facebook-release-candidate`, `8e08409`, clean at inspection.
- `/Users/juliodominguez/Documents/Codex/2026-10-21/let-s-prep-the-wholesale-os/integration`: `codex/wholesale-integration-review`, `c63f7d5`, two untracked duplicate-named schema files. Left untouched.
- `/Users/juliodominguez/Documents/Codex/2026-10-20/a-review-of-the-wholesaleos-github/facebook-release`: `codex/facebook-release-candidate`, `4480112`, clean at inspection.

Their relationship to the deployed baseline has not been verified. Do not reconstruct or merge an unpublished candidate from these references. Historical memory suggested prior paused Facebook work; current provider, schedule and deployment state was not queried.

## Exact resume steps

1. Enter `/Users/juliodominguez/Documents/Codex/2026-10-25/wholesaleos-acquisition-automation-prd-version-1/app`.
2. Check branch/status; pull its upstream with `git pull --ff-only` before changes. Preserve unrelated work.
3. Read this file, `IMPLEMENTATION-PLAN.md`, `SCHEMA-MAPPING.md` and `MIGRATION-AND-TEST-PLAN.md`. Continue `codex/acquisition-foundation` (production-based); do not switch back to the older planning branch for code work.
4. Load the Supabase skill and inspect affected function bodies/dependencies beyond the captured signatures; verify platform/provider controls without retrieving unrelated secrets. Read current official provider docs when implementing APIs.
5. Continue the shared foundation with workspace-bound legacy identities, authorization bridges, contact permissions/eligibility and durable ingestion. Use the captured mapping/conflict list to extend equivalents; do not replay historical migrations or touch held SMS work.
6. Update this checkpoint with concrete evidence, changes, remaining blockers and next action; commit and push each completed update.

## Validation and external effects

Implementation is local and tested as recorded above; migration files are proposals for later approval. No production database, provider configuration, scheduling, advertising, outreach, mail, offer transmission or contract execution changed. No production rollout is claimed. Git commit/push completion is reported separately after verification; inspect branch upstream and latest log when resuming.
