# Backup and restore isolation review — October 22

Status: procedure under review; no export, credentials, role or restore created.
This document does not certify the backup gate.

## Confirmed behavior

The inspected official CLI v2.79.0 data-dump filter leaves cron and net included;
its schema dump excludes platform/extension schemas. Production metadata confirms
cron.job, cron.job_run_details, net.http_request_queue and net._http_response.
Vault has a secrets table and decrypted-secrets view; their contents were not read.
The CLI source excludes Vault and role passwords. Keep those exclusions.
A default logical restore therefore also needs an explicit job/queue isolation
plan; logical does not automatically mean non-sending.

## Proposed procedure and acceptance

1. Establish an approved maintenance boundary or consistent exported snapshot.
   Separate unsynchronized schema/data dumps are not a consistency guarantee.
2. Use the existing database password entered in a protected local prompt. Do not
   paste it in chat, command arguments, Git or logs. If unavailable, separately
   review CLI-created access, its privileges, credential handling and lifetime;
   do not assume it is read-only or self-expiring.
3. Use a private local directory outside both Git checkouts, mode0700, files0600.
   Establish protected storage and retention before copying customer/Auth data.
   Nothing containing rows or credentials goes to Git, PRs, CI or external storage.
4. Capture roles without passwords, application schema and data, migration history,
   Auth/Storage custom schema changes, extensions, grants, sequences and non-secret
   configuration. Inspect exact dump scope rather than assuming the default includes
   everything. Preserve consent, DNC, suppression, paid-unknown and delivery receipts.
   Vault/key material is excluded and any dependency on it remains an explicit gap.
5. Preserve scheduler and network-queue evidence separately in protected archives.
   Build a distinct restore input that never inserts runnable cron jobs or outbound
   network requests. Do not delete them from production or edit the only backup.
   Application queues and receipts must be preserved; isolation must prevent their
   execution rather than erase unknown outcomes to make the restore pass.
6. Before loading rows, provision a compatible isolated Supabase/PostgreSQL target
   with outbound networking blocked and all job/worker/application dispatch disabled.
   Plain native PostgreSQL without required extensions is not a platform restore.
   No paid project, Docker installation requiring terms, or overwrite of the existing
   restore project is authorized by this procedure. Quote/review those actions first.
7. Restore transactionally with error-stop behavior. Verify source/target table counts,
   constraints, policies, grants, function fingerprints, migration history, receipt
   retention, task ownership and representative read-only application access. Check
   that jobs/requests remain inactive and no provider activity occurred throughout.
8. Record exact snapshot boundary, hashes, tool versions, target and results privately.
   A file existing is not restore proof. Keep the release gate open on any omission.

Before execution, access, protected storage, compatible isolated target and snapshot
consistency remain to resolve. No new paid resource or security access is implied.
A pre-upgrade backup is forensic recovery material; do not restore it over newer
consent, refusals, suppressions, paid holds or provider receipts after launch.

Sources inspected:
- https://github.com/supabase/cli/blob/v2.79.0/pkg/migration/dump.go
- https://github.com/supabase/cli/blob/v2.79.0/pkg/migration/scripts/dump_data.sh
- https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore
