# Buyer profiles in the acquisition flow

Status: published in90f9c324ef4ccd4c30dae0f8fcbe1a4ed74680e5 after local database, gateway and UI acceptance. See CURRENT-STATUS.md for exact successor CI; production activation is separate.

## Operator process

After the reviewed contract enters disposition review, open **Prepare buyer profiles** in step5. This keeps buyer preparation beside the contract process and within the selected workspace.

1. **Choose or add a buyer.** Refresh the bounded list, review an existing profile or add a new one. Historical global buyers are not automatically adopted into the workspace.
2. **Enter buyer details.** Record contact details, ZIP codes, property types, investment strategies, price/repair preferences and reported closing time. Explain the source. Leave unknown values blank; an explicit zero remains zero.
3. **Review and save.** Inspect the summary before saving. These are self-reported details awaiting verification. Saving does not authorize contact, distribute the property, approve financing or select a closing party.

Closing the editor releases adjacent contract controls. While editing or recovering a save, the app holds workspace/contract navigation to avoid losing the active request. Contact fields are optional; the list omits them and details require an explicit profile read.

## Recovery and stale information

The app retains the exact request before sending it. If the response is lost, use **Retry saved buyer request**. Reloading preserves the original request in that browser tab. The server returns its historical receipt without creating a second profile/revision. A later rejection cannot prove that an earlier request did not commit, so it must not erase an uncertain request. Do not manually clear browser storage to bypass this hold.

New saves recheck current access and revision. If another edit or an acquisition pause intervenes, return to the buyer list and reload before reviewing again. Paused acquisition permits authorized historical reads and exact recovery, but no new saves. Revoked membership/session denies both new activity and historical replay. Corrupt recovery data requires reconciliation rather than guessing a replacement request.

## Implementation and boundaries

- Canonical `buyers` rows hold nullable workspace ownership and exact revision; legacy rows remain unassigned.
- Private immutable `acquisition_buyer_versions` stores exact input, provenance note and request/revision metadata. Contact/provenance payloads are not exposed through raw tables.
- The mounted workspace buyer routes use the caller's authenticated database context. Owner/admin membership, MFA, active profile/session/workspace and the acquisition gate are enforced server-side; browser controls do not grant authority.
- List/detail projections require the canonical row's exact latest private revision. Legacy rows and incomplete private history are excluded. Caller and agency roles have no buyer-profile access.
- Legacy service-backed buyer APIs and buyer views exclude acquisition rows. Existing relationship tables reject scoped buyer references until controlled matching/closing writers exist. Trusted one-way email suppression remains available.
- Profile persistence is not buyer verification, eligibility or selection. Evidence-based verification, closing capability, explainable matching, reviewed packages/disclosures and controlled transaction milestones remain separate implementation work.

## Migration and compensation

Candidates116–118 reuse existing entities and add controlled private history/read/write functions. See SCHEMA-MAPPING.md and the manifest for exact filenames/hashes. They have not been applied to production.

If this capability must be withdrawn after an approved deployment, pause new acquisition operations and revoke authenticated execution of the buyer public wrappers and their private entry points through a reviewed forward migration. Preserve canonical scoped rows, private versions and audit history. Retain legacy filters, restrictive RLS and relationship guards. Never remove workspace ownership or expose private history to restore the old global workflow. Restore read access only after the replacement projection and membership checks are verified.

## Evidence

- Full118 baseline rehearsal3031:376 workflows,26 access checks,167 existing gateway checks;24 historical rows across22 tables and103 definitions preserved. `evidence/2026-11-01-buyer-118-full-result.json`.
- Backend4746 passed,10 skipped. `evidence/2026-11-01-buyer-118-backend-result.json`.
- Final frontend1107 passed, build passed, no new lint findings; parent integration48 passed (including three buyer cases).
- Synthetic browser desktop1280×900 and phone375×812: lost reply, reload, identical recovery and one retained buyer record. Screenshots visually reviewed; no console errors. `evidence/buyer-profiles-2026-11-01/`. This tests real components with a synthetic adapter, not the server or hosted Auth.
- All175 actual gateway checks, including buyer-specific mounted API checks, pass in the focused complete-catalog runner. The final populated migration-role rehearsal19435 passed376 workflows and175 gateway checks; see evidence/2026-11-01-buyer-118-publish-result.json for the terminal result and CURRENT-STATUS.md for the next active batch. Do not treat baseline167 checks as evidence of this newly added journey.
