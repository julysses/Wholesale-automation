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

The assessment is a deterministic calculation, not an additional human approval. The API can be called by an authorized application flow. Automatic integration with identity-review completion and canonical underwriting reservation remains to be wired; no new worker or scheduler is installed by this migration.

## Evidence and release boundaries

Disposable PostgreSQL tests cover all five classifications, complete Dallas/Collin records, explicit zero, malformed contact, ambiguous price, authority denial, reviewed-repeat invalidation, concurrent idempotent recording, immutable history, tenant/session/service-role denial and activation holds. The first outside-territory fixture correctly failed the existing county constraint; the test now uses an allowed Dallas-to-Collin change and separately verifies Denton rejection. The production constraint was not weakened.

The integrated Facebook journey covers duplicate assessment recording, exact replay and invalidation back to incomplete after identity-link revocation. This is real SQL behind an isolated HTTP adapter, not live Meta/PostgREST acceptance. Full-schema upgrade, production approval, retained-evidence policies, reviewer UI assessment display and downstream consumption remain release requirements.

Compensation: disable acquisition activation to stop new snapshots and invalidate qualified links; retain original submissions and history. Use identity revocation/correction for incorrect links and append a fresh assessment when authorized. No destructive rollback or historical migration replay is required.
