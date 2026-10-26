# Versioned intake qualification

Migration `20261026181452_acquisition_intake_qualification.sql` adds a deterministic screening assessment and immutable assessment history. It extends the existing intake/identity workflow without rewriting original seller submissions, CRM leads, canonical property bindings or consent records.

## Decision rules

The `intake-qualification-v1` policy evaluates rules in this order:

1. Invalid preparation structure or conflicting/ambiguous answers require human review.
2. Explicit denial of authority or interest is unqualified, even if a property has been reviewed.
3. A currently valid reviewed repeat-inquiry association is duplicate. Missing information remains listed; the repeat does not become a separately qualified opportunity.
4. Missing required seller answers or no valid normalized phone/email produces incomplete. A malformed contact stays missing rather than being silently accepted.
5. Unresolved authority or price requires review. Explicit zero remains a supplied price; missing and ambiguous prices do not become zero.
6. Disabled acquisition activation, no current canonical property review, or missing canonical territory requires review.
7. A canonical property outside the initial territory is unqualified. The existing county table currently enforces TX and Dallas/Collin through database checks; this defensive rule does not broaden that schema or authorize expansion.
8. Otherwise, complete intake with a current reviewed Dallas/Collin property is qualified for further acquisition analysis.

Qualified is a screening status. It is not ownership/title verification, an independently confirmed valuation, permission to contact, offer approval or authority to execute a transaction. Those flags remain false. Market-data requirements and underwriting completeness are separate.

## API and persistence

- GET `/api/acquisition/workspaces/{workspace}/intakes/{intake}/qualification-state` computes current screening facts and returns an evidence hash, assessment sequence, latest stored version and `assessment_current`.
- POST `.../assessments` takes only a request UUID, expected sequence and evidence hash. Classification cannot be supplied by the client. The server re-evaluates under locks and appends the result plus an audit event.
- GET `.../assessments?before={sequence}&limit=20` reads scoped history in descending sequence order (maximum page size 50).

Each version preserves the policy version, original intake hash, reviewed identity reference/sequence, current target snapshot/hash, canonical territory, missing fields, reasons, authority flags and recording actor. Original source answers and identity review records remain independently immutable. A target change, identity revocation, approval-authority change or activation hold invalidates a previously saved result. Historical qualified/duplicate records remain visible as history, never silently presented as current.

Actual owner/admin/operator membership and an approved live session are required. Caller/agency/unrelated access is denied by existing role helpers and table RLS. Direct service/application mutations and truncate are revoked. Recording locks activation, workspace, request authority, intake, identity-review authority and canonical target through commit. Exact request retries reconcile the original result; changed identity or stale expected state fails. Original CRM data remains separate and unchanged.

The assessment is a deterministic calculation, not an additional human approval. The API can be called by an authorized application flow. Automatic integration with identity-review completion remains to be wired; canonical underwriting reservation now snapshots qualification atomically as described below; no new worker or scheduler is installed by this migration.

## Evidence and release boundaries

Disposable PostgreSQL tests cover all five classifications, complete Dallas/Collin records, explicit zero, malformed contact, ambiguous price, authority denial, reviewed-repeat invalidation, concurrent idempotent recording, immutable history, tenant/session/service-role denial and activation holds. The first outside-territory fixture correctly failed the existing county constraint; the test now uses an allowed Dallas-to-Collin change and separately verifies Denton rejection. The production constraint was not weakened.

The integrated Facebook journey covers duplicate assessment recording, exact replay and invalidation back to incomplete after identity-link revocation. This is real SQL behind an isolated HTTP adapter, not live Meta/PostgREST acceptance. Full-schema upgrade, production approval, retained-evidence policies, live provider and PostgREST acceptance remain release requirements.

Compensation: disable acquisition activation to stop new snapshots and invalidate qualified links; retain original submissions and history. Use identity revocation/correction for incorrect links and append a fresh assessment when authorized. No destructive rollback or historical migration replay is required.

## Dashboard screening panel

The selected intake review now displays the freshly evaluated classification, reasons, missing fields, canonical territory and policy version. Saved history is separate, with an explicit stale warning whenever its evidence hash no longer matches. Loading/access failure hides cached current status. Responses claiming ownership verification, contact permission, outreach or a binding offer are rejected rather than displayed as authorized.

Saving a snapshot refreshes the state first and sends only request ID, expected sequence and evidence hash. An unknown response keeps the exact request for explicit retry; identity edits and closing the selected review are blocked until the outcome is reconciled. Identity decisions or evidence refreshes trigger a new qualification read, while queue refresh preserves an unresolved save. No automatic retry or new execution authority is introduced. This manual snapshot control is not an extra approval gate: current screening is computed on read; the dedicated underwriting API now snapshots automatically; its dashboard control remains to be connected.

The synthetic browser fixture verifies incomplete status, missing answers, successful snapshot recording, matching-current confirmation, disabled redundant saving and saved history with no console errors. Screenshot: `evidence/2026-10-26-qualification-browser.png`. Component tests additionally cover stale qualified history, changed hashes, uncertain responses, access failure, identity revision changes and rejection of authorization-bearing responses. This is not live PostgREST/provider acceptance.

## Qualified intake to canonical underwriting

Migration `20261026184848_acquisition_intake_underwriting_handoff.sql` adds `acquisition_analysis_intakes`, an immutable workspace-scoped provenance link from existing `deal_analyses` to the original intake, qualified assessment and reviewed canonical identity. Composite foreign keys enforce matching workspace and source identity; authenticated owner/admin/operator SELECT uses membership RLS. Direct writes, deletes and truncate are revoked.

POST `/api/acquisition/workspaces/{workspace}/intakes/{intake}/underwriting/scenarios` accepts a request UUID, fresh qualification evidence hash and explicit validated underwriting inputs. It does not accept a canonical lead override. Under authority/source/target locks, the database re-evaluates qualified status, records the assessment and reserves the canonical property scenario in one transaction. Failed input validation leaves neither assessment nor reservation. The shared dedicated calculator then runs against those reserved inputs. The response includes fresh intake provenance and `qualification_current`; historical results may remain readable when false.

Exact retries reuse the same scenario and assessment. A request cannot adopt an existing manual scenario. Intake-based scenarios additionally require current identity evidence and reviewer authority at calculation completion, offer proposal and amount approval. Revocation or changed canonical evidence marks prior offers noncurrent without erasing history. Rejection, withdrawal and approval revocation remain possible. Ordinary manually reserved scenarios keep their existing controls.

Compensation: hold acquisition activation and revoke/correct the reviewed intake identity as appropriate; retain immutable assessment/analysis provenance. Reassess and reserve a new version after correction. Do not drop provenance to make an obsolete analysis appear current. No production migration is authorized by this implementation. The dashboard handoff, real PostgREST acceptance and comprehensive production-schema upgrade test remain pending.
