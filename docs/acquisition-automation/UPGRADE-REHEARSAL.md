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

## Executable baseline restore — October 29, 2026

Run `python scripts/run_offline_tests.py --acquisition-upgrade-baseline` with backend dependencies and PostgreSQL 17 installed (`PG_BIN` selects the binary directory). The runner rejects a different PostgreSQL major version, creates and removes its own Unix-socket-only cluster, accepts no hosted database URL and retains the offline runner's cleared environment/network guard. The older Facebook restore and its fixtures are unchanged.

`pipeline/integration/rehearse_acquisition_baseline.py` verifies the snapshot hash and separate read-only ownership capture, restores the application catalog as its captured postgres owner, preserves view security and ACLs, and compares every captured application category with the same catalog query. ACL entry ordering is normalized without dropping grantees, grantors, privileges or grant options. The display search path includes extensions to match the captured expression rendering; function definitions and stored search paths are still compared. Managed Auth/net/vault/cron are explicitly inert fixtures; Storage is not installed by this baseline stage.

The final run passed for 103 tables, 17 views, 122 functions and 95 migration identities, including exact captured constraints/indexes/policies/triggers/columns/defaults/ACLs and schema/relation/function ownership. Transactional negative probes confirmed rejection of a removed foreign key, widened table grant, altered security_invoker view, altered function security and changed table owner; each was rolled back and the clean baseline reverified. No production rows were copied and no candidate acquisition migration was applied.

Hosted CI still uses PostgreSQL 16 for its existing focused tests. Do not wire this snapshot comparison into that runtime or discard PostgreSQL 17 privileges to force compatibility. A matching PostgreSQL 17 hosted runtime and the populated candidate upgrade remain next work; this local result is not hosted or managed-platform acceptance.

## Populated candidate upgrade — October 29, 2026

`--acquisition-populated-upgrade` now restores and verifies the baseline, installs the explicit Storage fixture, seeds synthetic historical records, and applies every candidate in `evidence/acquisition-upgrade-manifest.json` in filename order. It rejects missing/extra candidate files, changed SHA-256 values and any candidate identity already present in the deployed ledger. All 45 candidate files were applied without editing their SQL or skipping foreign keys. SQL function-body validation is enabled during candidate application.

The final result in `evidence/2026-10-30-populated-upgrade-result.json` confirms preservation of 24 historical rows across 22 populated tables, checking original columns across all 103 baseline tables. Seeds include CRM/property, Facebook submission, held SMS job/session/turn, expired owner-retest authorization, generation reconciliation, audit, queue, campaign/creative and task history. A Storage object fixture is also preserved. Both SMS schedulers and acquisition activation remain disabled; integration/signing configuration is empty, and no net/cron/vault execution state is created. This is synthetic representative coverage, not a backup of customer data or coverage of every historical business state.

### Platform authority and reproducible dependency

Initial runs stopped at Storage permissions because the original reduced fixture omitted the postgres schema/table grants. Read-only metadata in `2026-10-30-upgrade-storage-authority.json` established actual Storage ownership/ACLs, postgres database ownership, non-superuser status and lack of Storage-owner membership. Supabase additionally grants policy-management rights through Supautils. The local runner now restores those relationships and uses the real extension with an allowlist limited to storage.objects and storage.buckets; it does not grant the migration role table ownership or superuser access. A subsequent missing database-owner relationship was corrected in the fixture, not in candidate migrations.

Official source: https://github.com/supabase/supautils, tag v4.0.0, pinned commit `7a22990746ec17b1a84cf2a097dda411222f8ec7`. The README's Table Ownership Bypass section documents policy_grants. Source was downloaded with GitHub CLI, safely extracted with Python 3.12 tarfile's data filter, and built with `make PG_CONFIG=/opt/homebrew/opt/postgresql@17/bin/pg_config PG_VERSION=17 all`. No make install or global package change occurred. The current disposable build is `/tmp/acq-supautils-pqh8r_gn/supabase-supautils-7a22990/supautils.dylib`; rebuild from the pinned source if it is missing. The deployed Supautils version could not be established from its version setting, so exact platform-version parity is not claimed.

Run with `ACQUISITION_TEST_SUPAUTILS` set to the explicitly reviewed absolute library path, then `python scripts/run_offline_tests.py --acquisition-populated-upgrade`. Only this test-library path and PG_BIN are forwarded through the scrubbed environment. The library is loaded only by the newly created local cluster; no hosted URL is accepted. The runner stops if the library is missing or the PostgreSQL major differs from the captured baseline. Linux builds use their generated shared-library suffix.

### Remaining acceptance

The populated migration/preservation stage passed. Authenticated workspace/RLS and complete application workflows must still be exercised against this upgraded full baseline, rather than only their smaller fixtures. Hosted PostgreSQL 17/Supautils CI setup, managed Auth/Storage/PostgREST/JWT behavior, live provider acceptance, production drift recheck and explicit migration approval remain outstanding. Existing CI focused jobs remain unchanged. No production SQL, permission, provider, scheduling or spending action was taken.


## Full-catalog access checkpoint

The populated-upgrade command now also executes `acquisition_upgrade_access.py` after migration and history checks. Its 19 named checks passed on the complete restored application catalog and candidate migrations; the saved result is `evidence/2026-10-30-full-catalog-access-result.json`. It tests actual SQL roles, workspace isolation, assignment-scoped caller projection, legacy lead restrictions, MFA, session/profile/membership revocation, idempotency and closed activation controls. All probe mutations roll back; the runner then rechecks the historical fingerprints. No grants or migration definitions were relaxed.

The synthetic JWT claim adapter remains a platform fixture. Full application workflow coverage on this baseline, real Auth/PostgREST/Storage transport, matching hosted CI, and production approval remain required. The existing focused workflow tests remain useful but do not close those gaps.


## Full-catalog application journeys

The populated rehearsal now runs eight existing application workflow cases on separate database copies of the fully upgraded catalog. `acquisition_upgrade_workflows.py` seeds synthetic users and properties without recreating schema or relaxing permissions. It reuses the API/calculator/SQL transport tests for Facebook intake identity and qualification handoff, four investment strategies and internal amount review, unsupported assignment buyer economics, missing market data, and a lost calculation response. All eight passed locally. Each copy is dropped, and original historical fingerprints are rechecked afterward.

This moves application workflow evidence beyond the focused schema fixture. It does not remove the simulated provider and PostgREST boundaries or establish live authentication or platform acceptance. The default focused harness database and its tests remain available unchanged in behavior.
