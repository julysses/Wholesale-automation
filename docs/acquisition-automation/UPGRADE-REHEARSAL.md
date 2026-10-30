# Full-candidate upgrade rehearsal — baseline preparation

## Verified baseline

The read-only query in `evidence/upgrade-catalog-query.sql` captured the current public/private/wholesale_ingest catalog and migration ledger in one query at 2026-10-30T03:00:51.255656Z. `evidence/2026-10-30-upgrade-catalog.json` contains 103 tables, 17 views, 122 full function definitions, 407 constraints, 113 non-constraint indexes, 127 policies, 28 triggers and 95 migration identities. No business rows, auth sessions, credentials or vault contents were selected. The snapshot does not include managed Auth/Storage definitions or their operational acceptance.

The report `evidence/2026-10-30-upgrade-baseline-report.json` records the catalog SHA-256 and differences from the older Facebook rehearsal. The older snapshot stops at 91 migrations / 20261019195321. Current production ends at 20261023221455 and contains three additional tables: public.facebook_lead_submissions, private.retell_owner_retest_authorizations and private.retell_generation_reconciliations. These must survive the acquisition upgrade with synthetic historical rows intact. Applying their local migration files blindly is inappropriate because deployed migration identities differ from some repository filenames.

The acquisition inventory's 120 objects are 103 tables plus 17 views, not 120 tables. Its function inventory contains signatures/security metadata and only two full auth-function bodies. It remains useful for mapping; it is not a complete restoration source. Read-only checks also confirmed that public.workspaces and public.acquisition_evidence_verifications are absent in production.

## Restoration gaps identified in existing code

`pipeline/integration/production_schema.py` restores the older Facebook snapshot. It must not silently become the current acquisition baseline. Its view recreation omits captured view options and grants; all 17 current views have security_invoker=true. A replacement/parameterized current-baseline restore must retain those options and verify resulting view security before testing RLS. Existing helper assumptions for enum/sequence/identity objects must fail explicitly if unsupported; this capture has none.

`scripts/test_acquisition_workspace.py` is deliberately a focused fixture. It omits unrelated foreign-key targets, installs synthetic permissive legacy policies and uses reduced auth/storage platform fixtures. Its 217 checks provide valuable focused evidence, but do not establish compatibility with all deployed objects or provider-managed schemas. The 48 API/database workflows have the same scope distinction.

## Next implementation contract

1. Add a separate, explicitly selected current-catalog restore path. Keep the existing Facebook baseline unchanged for its historical tests. Restore in a newly created disposable Unix-socket database with no external HTTP, cron, provider worker or inherited secret environment; do not point this runner at a supplied hosted URL.
2. Recreate all captured application tables, exact columns/defaults, constraints, indexes, full function bodies, triggers, views/options, table/function/view/schema ACLs and default ACLs. Enumerate any platform substitutions (Auth, Storage, net, vault, cron) in the report; these are test fixtures, not live acceptance.
3. Compare the restored catalog against the snapshot before applying candidate migrations. Fail on missing definitions, skipped foreign keys, lost security_invoker options or widened grants rather than smoothing over restore errors.
4. Seed representative synthetic legacy CRM, county/property, Facebook receipt and paused Retell authorization/reconciliation records. Save row fingerprints and disabled scheduler states. Run the exact ordered acquisition migration candidate without replaying already-deployed history. Preserve the migration-file manifest and hashes.
5. Verify historical row fingerprints, relationships, views and disabled controls after upgrade; run actual role/session/RLS, idempotency and acquisition workflow probes against this restored baseline. Verify that no external dispatch or automatic activation is possible. Report unsupported platform behavior explicitly.
6. Independently complete managed Auth/Storage/PostgREST/JWT acceptance and refresh production drift checks before requesting production migration approval. A successful local rehearsal is not deployment authority.

## Current outcome

Fresh catalog capture and baseline comparison completed; the current-catalog restoration and full populated acquisition upgrade have not yet run. No production SQL mutation or migration occurred. This document is an implementation handoff, not a passing MIG-001 release certificate.
