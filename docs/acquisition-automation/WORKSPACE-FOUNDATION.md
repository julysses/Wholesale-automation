# Workspace foundation implementation

## Follow-on: request identity and related-record isolation

When ACQUISITION_ENABLED is true, DatabaseIdentityMiddleware supplies request-local caller credentials to protected API, internal and legacy paths. The shared CRM client factory uses a public Supabase key with the caller's Authorization token and disables session persistence/refresh. Buyer and webhook factories delegate to it; protected monitoring HTTP uses the same identity. Missing/duplicate/malformed auth never falls back to service role. Async context resets after each request and propagates into supported Starlette threadpool operations.

Explicit public form/config/readiness endpoints and signed provider/worker endpoints keep their existing server workflow. Those handlers remain responsible for signature/secret/input verification. Startup settings loading is not a request data surface. No provider callback or worker was exercised live.

Cached SQLite CRM instances are also blocked during scoped requests. `/v1` and the local rescore route return 409 in this mode until replaced with workspace-aware workflows. Legacy behavior with the flag disabled remains unchanged. Do not treat disabled-mode compatibility tests as proof that every old service-only write RPC works in scoped mode; many intentionally reject authenticated execution until adapted.

Migration `20261026030633_acquisition_related_record_isolation.sql` derives read permissions for existing tables carrying UUID lead_id, deal_id or property_id references. Scope is resolved through canonical workspace_leads, deals and county properties. Conflicting parent workspaces hide the row; owner/admin/operator membership permits the appropriate read. Raw authenticated writes to bound children remain denied. It adds no broad grants and does not copy or reparent records. A county property trigger prevents changing the lead link once its identity is bound.

Validation now includes 25 real PostgreSQL cases and the full offline backend suite: 1,214 passed, 10 local-database-dependent tests skipped. Twenty-five identity tests cover threadpool/parallel isolation, malformed/duplicate tokens, exceptions, public/server boundaries, SDK credential construction and the real application's auth-to-reader wiring. Actual SDK header behavior was inspected locally without network access. Full PostgREST/103-table upgrade acceptance is still pending.

Remaining release work: coordinate database RPC activation with the application flag; replace necessary legacy write RPCs/local workflows; scope buyers/campaigns and JSON-linked/orphan historical evidence; complete full upgrade and UI acceptance. Until then, do not apply the candidate to production or enable the feature. Compensation is to leave the feature disabled and preserve added metadata/audit history; never restore service-role fallback within scoped requests to work around a denied RPC.

## Follow-on: account containment and canonical lead binding

Migration `20261026025259_acquisition_legacy_access_boundary.sql` adds acquisition_only to profiles and a workspace_leads relation to existing canonical leads and optional verified county properties. Binding is explicit, audited and immutable through application table grants; it does not copy property or owner records. An existing property must already reference the selected lead. A shared phone never establishes identity.

Non-owner memberships trigger sticky acquisition-only access. Revoking a membership does not reopen legacy access. Existing non-owner memberships are restricted during upgrade, and preexisting platform-admin caller/agency memberships abort the upgrade for review. Full administrator identities must not serve as limited caller accounts.

Restrictive RLS blocks acquisition-only users from existing public/ingestion tables except explicitly scoped surfaces. Scoped leads can be read directly by workspace owner/admin/operator roles, but cannot be directly inserted, updated or deleted through authenticated table access. Callers/agency users receive assigned lead summaries through a bounded private RPC, with no phone/email projection and no raw-table access. Revoked memberships, suspended profiles/workspaces, missing sessions and caller MFA failures deny access.

Additional endpoints: POST `/api/acquisition/workspaces/{id}/leads` binds `{lead_id, property_id?}`; PUT `/api/acquisition/workspaces/{id}/leads/{lead_id}/assignment` accepts `{user_id}` (null clears assignment); GET `/api/acquisition/workspaces/{id}/leads?after=<uuid>&limit=20` returns a keyset page (maximum 50). All use user-scoped PostgREST RPCs. Binding requires both legacy platform-admin and workspace-owner authority; assigning requires workspace owner/admin.

Legacy HTTP routes now deny acquisition-only profiles before reaching service-backed handlers, while schema-compatible profile reads permit code to run before the new column exists. Public inquiry/config routes and signed provider callbacks keep their existing boundaries.

**Still a release blocker:** a legacy user's existing service-role handler can bypass the new RLS boundaries. Do not bind production resources until those handlers/RPCs are scoped, and workspace ownership has propagated to related business records. Database RLS tests alone do not close that API-level gap. Contact permissions, eligibility, agency cohorts, provider acceptance and the full-schema upgrade rehearsal remain pending.

Current validation: 22 real PostgreSQL cases and 121 combined targeted backend cases pass. The fixture now reconstructs inspected profiles, audit_logs, leads, county properties and campaigns; unrelated lead FK targets are intentionally omitted, so this remains a focused migration test. Compensation: keep features off, retain binding/audit history, revoke incorrect assignments/memberships through audited functions; never clear acquisition_only automatically during revocation or replay a backfill. Returning an account to legacy access needs explicit privileged review.

Candidate branch: `codex/acquisition-foundation`, from deployed `c8673c170368bc8c44974fd304fac5af3fcf6e8c`. The acquisition routes default to 404 unless `ACQUISITION_ENABLED=true`. No setting is enabled by this commit.

## Database contract

Migration `20261026024157_acquisition_workspace_foundation.sql` creates workspaces and memberships and extends audit_logs with workspace ownership. Existing public.profiles continues to hold global account approval and role. Workspace roles are independent of the existing admin/user enum. Nothing backfills membership or assigns existing CRM/county records.

Approved global admins with a current Supabase auth session can create a workspace through the authenticated RPC. Creation atomically creates the owner membership and audit entry. A client-generated UUID makes an exact retry idempotent; identity/name conflicts fail closed. Owners manage privileged membership; workspace admins manage operator/caller/agency membership but cannot grant or change owner/admin privileges. Revocation and role changes serialize per workspace so concurrent removals cannot remove the last active owner.

RLS derives auth.uid from verified JWT claims and checks an existing auth.sessions row bound to that user/session_id, session not_after, current approved profile, active workspace and current active membership. Caller and agency roles additionally require aal2. User metadata is never an authorization source. Full session policy timeouts beyond not_after and caller cohort enforcement are subsequent acceptance work.

New tables grant authenticated SELECT only. Mutations use private security-definer helpers with an empty search path; public RPC wrappers are security invoker. Service-role credentials do not receive administrative RPC execution. Scoped audit events reject UPDATE/DELETE even for service_role, and application roles cannot TRUNCATE the audit table. Existing unscoped audit inserts remain compatible. Database owners remain privileged administrators; this is application immutability, not protection against a malicious DBA.

## API contract

- `GET /api/acquisition/workspaces`: caller-visible workspaces, capped at 100.
- `POST /api/acquisition/workspaces`: `{id, name}`; approved global administrator required by SQL.
- `GET /api/acquisition/workspaces/{id}/memberships`: owner/admin sees workspace memberships; other members see their own, capped at 100.
- `PUT /api/acquisition/workspaces/{id}/memberships/{user_id}`: `{role, status}`; SQL enforces current administrator rights and target-role restrictions.

The server uses the caller's Bearer token plus a publishable/anon key, never the service key. Database failures are sanitized; uncertain mutations are not automatically retried. Callers can retry a workspace creation using the same UUID; membership mutation retries are no-ops when state already matches. Current list endpoints are capped; pagination is pending UI work.

## Validation and release limits

15 real PostgreSQL cases exercise RLS, session/profile/membership revocation, caller MFA, raw-write rejection, cross-workspace access denial, scoped audit immutability, legacy audit preservation, parallel creation and concurrent last-owner protection. 14 API cases verify flags/auth forwarding, validation and safe failure behavior. Existing auth/Facebook/Retell suites pass alongside them (111 total backend tests).

The test runner restores the exact inspected profiles/audit column and constraint shapes and a minimal synthetic auth model; no production rows or credentials are loaded. It uses a temporary Unix socket with TCP disabled. Full production-shaped migration rehearsal remains required before production approval. Current Supabase RLS guidance was consulted: https://supabase.com/docs/guides/database/postgres/row-level-security .

**Do not activate yet:** legacy shared tables/endpoints are not workspace-scoped by this first migration. Caller and agency users must not be provisioned into production until legacy-access/cohort restrictions are implemented and tested. Workspace status suspension currently requires a database administrative operation; no public suspension endpoint is provided yet. No outbound eligibility or channel activation is implemented by this slice.

## Compensation

Before apply: no recovery operation needed; revise and rehearse the candidate. After an approved apply: disable ACQUISITION_ENABLED and retain workspaces, memberships and audit history. Restore the prior application version only after compatibility verification. Do not drop membership/audit evidence, reopen broad scoped-audit reads or remove the last-owner guard. Misassigned memberships should be revoked through the audited owner operation. Existing legacy rows have no workspace backfill to undo.

## Coordinated activation guard

The activation migration adds a private, disabled singleton and immutable transition history. No application-role grants or public activation RPC exist. A separately authorized database operator must record the approval reference, verified 40-character application revision and timestamp before enabling enrollment and binding. Confirm the actual deployed revision, `ACQUISITION_ENABLED=true`, user-JWT database routing, functional legacy replacements and acceptance evidence before that separate change. A supplied revision string is an attestation, not an automatic deployment check.

Apply the complete reviewed migration bundle under a maintenance boundary before exposing acquisition RPCs; do not expose the earlier foundation migrations alone while the final guard is absent. No production apply is authorized by this document. The current implementation branch remains deployment-disabled.

Compensation: an authorized database operator sets `private.acquisition_activation.enabled=false`. This serializes with enrollment/binding transactions and prevents new workspaces, enrollments, bindings and assignments. It preserves data, existing RLS and acquisition-only account flags. Revocation/suspension remain possible. Do not revert the application to legacy service-role operation while scoped data exists. Disabling this gate does not stop existing reads, signed server workflows or future providers; those require their own fresh eligibility and phase controls. Never delete history or unbind records as rollback.
