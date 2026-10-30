# Acquisition retention implementation contract

October 30, 2026. Source inspection, not approval to delete or retain live seller data indefinitely. Implement this before the Phase 1 monitored retention requirement can be accepted. No retention schedule is installed by this document.

## Observed storage paths

| Data class | Current source and behavior | Consequence |
| --- | --- | --- |
| Native webhook envelope | `webhook_jobs.payload`, `acquisition_raw_body`; integration retention_days 1–90, default 30; expiry stamped at acceptance | Existing `purge_acquisition_payloads` clears these two fields after the stored deadline and retains IDs/hashes plus audit |
| Retrieved Meta form answers | `tools/acquisition_intake.py` copies field_data and custom_disclaimer_responses into provider_evidence, plus normalized seller assertions and evidence; SQL stores this in `seller_intakes.prepared_answers` | Clearing the webhook receipt does not clear the retrieved lead answers or consent evidence |
| Canonical lead | Completion writes the existing `leads` record and workspace binding; `zz_acquisition_intake_retention` forces keep/review-required for facebook_acquisition | Legacy unattended cleanup deliberately cannot dispose of the acquisition CRM record |
| Attribution | Campaign links/lead sources derive external IDs from the intake's provider_evidence | Redaction must preserve the minimum immutable attribution needed or explicitly mark unavailable provenance; it cannot silently rewrite attribution facts |
| Subsequent reviews | Identity/qualification/underwriting/offer history depends on the lead/intake and versions | Retention needs a defined per-data-class policy and transaction state, not a blanket cascade delete |
| Mail supporting files | Separate evidence registry/policies/object storage and signed verification/binding history | Inbox purge does not manage file bytes, evidence metadata or approvals; file retention needs its own reviewed storage lifecycle |

The receipt purge uses receipt-row locking and SKIP LOCKED, bounds batches to 500 and appends one purge audit. It is service-only. It does not inspect an acquisition legal-hold registry, because none was found in the acquisition migrations. It does not establish CRM deletion, purge uploaded evidence or send an owner notification. These are limits of the current implementation, not reasons to widen its authority silently.

## Policy decisions needed before live activation

Record reviewed durations separately for raw webhook envelopes, original form answers, normalized unconverted lead data, consent/suppression evidence, transaction records and uploaded review files. Define who may place/release an exception or preservation hold and what review evidence is required. Do not use the 30-day envelope engineering default as automatic approval for all classes.

Preserve opt-out and suppression enforcement when deleting ordinary seller details; deleting a lead must not make the same contact eligible again. A lawful retention basis and minimum suppression identity are policy decisions; the implementation must enforce the approved policy version without guessing it. Completed/active transactions and unresolved disputes need explicit policy treatment before automatic disposal.

## Implementation sequence

1. Add versioned, initially inactive retention policies and auditable per-record holds/release records using existing workspace membership/MFA controls. Inventory current constraints, dependencies and policies before a new migration. Use actual source identity and policy evidence; no client-supplied bypass.
2. Build a workspace-scoped read-only retention preview. Group candidates by data class, current lifecycle state, deadline and blocking reason. Return bounded counts/references; no seller answer bodies. A preview authorizes nothing and must be refreshable in the existing app review process.
3. Implement a separately authorized batch reservation and exact-request execution record. At execution, recheck current policy/holds/dependencies and serialize with intake completion, recovery, suppression and relevant transaction writes. A hold that commits before deletion must prevent it; use real contention tests.
4. Redact/purge the approved sensitive classes through narrowly scoped functions. Preserve historical IDs, required consent/suppression facts, approved attribution and immutable minimal audits; mark evidence unavailable where appropriate. Never disable immutable triggers globally or cascade-delete canonical owners/properties to simplify a purge.
5. Add a disabled monitored runner only after those controls exist. Bounded runs must report counts by actual data class, withheld counts/reasons, failure/unconfirmed status and a durable run reference. Exact retries reconcile the original run. Do not label receipt-only purging as seller-data deletion.
6. Validate with synthetic expired/nonexpired records, held/released records, active transactions, matching contact suppressions, lost responses, concurrent hold/processing requests and cross-workspace access. Then run approved hosted Auth/Storage acceptance and verify alert delivery before requesting live retention activation.

## Immediate boundaries

Keep live inbox/worker acceptance and automatic purge deployment unapproved until the release packet's retention requirements are resolved. Do not extend existing deadlines or delete copied intake answers merely to make a test pass. Continue other authorized implementation work while policy decisions and hosted acceptance remain pending.

Compensation must stop the runner and disable its execution gate while preserving all run, hold, policy and audit history. Deleted source bytes cannot be recreated by a rollback migration; backup/restore and irreversible-action approval must be explicit in the eventual execution proposal.
