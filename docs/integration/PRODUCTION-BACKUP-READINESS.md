# Production backup readiness — October 22, 2026

Read-only dashboard review; no Restore/Enable/Create action was taken. The database
connector does not expose backup history, so the signed-in dashboard supplied it.

The production project lists eight physical backups, October15–22, all COMPLETED
on its Restore to New Project page. Latest: October22 at12:13:03 UTC. This is provider
completion/availability evidence, not a fresh restore test or a current pre-release
backup. The dashboard also lists the October8 restore rehearsal as COMPLETED at
17:53:43 UTC. That older rehearsal does not verify today's backup or current app.

Point-in-time recovery is not enabled: its page offers an add-on. No add-on was
selected or purchased. Storage metadata was counted read-only at23:37:36 UTC:
0 buckets and0 objects. Database backups exclude file contents, but there are no
current Supabase Storage objects to copy at this observation. Recheck at release.

Supabase documents that native clones may immediately start copied external-operation
jobs. It recommends logical restoration when jobs/hooks need review first. Current
production's active monitoring/retention jobs therefore need isolation review; no
harmless external behavior is assumed. No customer data was exported.

Cloning also adds compute charges and needs some configuration rebuilt separately.
No clone, credential or paid add-on was created. The existing restore project remains
intact. A current restorable backup and approved maintenance boundary remain required before
schema application. Do not restore a pre-upgrade backup over new consent/receipt data
as routine rollback; preserve post-release evidence and use a compatible repair.

Provider status at observation: API Gateway Request Issues is Monitoring/degraded,
with Data APIs and Project Creation includingus-west-2. This does not establish an
app outage or explain individual application errors. Recheck status and perform
actual signed-in/API/database acceptance before the release decision. No automatic
monitor or repeated poll was created.

Sources:
- Production dashboard backup and restore-history pages (authenticated observation).
- [Supabase clone documentation](https://supabase.com/docs/guides/platform/clone-project).
- [Current API Gateway incident](https://status.supabase.com/incidents/01M5J8ZQ04EZXAYF10Q75MGC1T).

Live app check: GET /api/health returned HTTP200 and the expected status/service
payload. Source inspection confirms this handler returns a constant process-health
response; it does not query the database or verify Auth/provider delivery. The web
reader's earlier access failure was not an app outage: the direct read succeeded.

A secure logical export connection is not currently configured in the known local
environment-file locations or process database-credential variables. No standard
PostgreSQL passfile exists, and the CLI is unlinked. No secret values were printed or fetched from browser storage. Do not
substitute a partial JSON/table export for a complete restorable backup, reset a
password, copy Vault secrets, enable paid PITR, or clone auto-running jobs just to
make this gate appear complete. A reviewed isolated restore path and secure existing
connection setup remain necessary before execution.

Exact observation: production-backup-observation-2026-10-22.json. No customer rows,
Auth hashes, files, keys or production data were copied; only metadata/counts read.


## CLI capability follow-up

Read-only project listing through the installed official CLI v2.79.0 succeeds.
This confirms existing control-plane authentication, not a database backup.
Review of that exact version's `internal/utils/flags/db_url.go` shows the linked
DB path calls `initLoginRole` when no database password is supplied. The request
uses `ReadOnly: false` and receives a role/password. It is not just a read-only
metadata connection. No link, dump, temporary login creation or password reset
was run during this check. Source was downloaded for inspection only.

The supported dump also runs PostgreSQL inside Docker. The current machine has
native PostgreSQL17 but no established Docker runtime. The documented complete
workflow separates roles, schema and data, with migration history handled
separately; a default schema dump alone is insufficient.

Next: establish an existing-password connection and a reviewed isolated restore
runtime, or obtain explicit authorization for the exact temporary-login method.
Do not print dry-run commands or connection strings: they can include credentials.
No current export or restore is certified by this investigation.

Sources:
- [Installed-version credential behavior](https://github.com/supabase/cli/blob/v2.79.0/internal/utils/flags/db_url.go)
- [Installed-version dump execution](https://github.com/supabase/cli/blob/v2.79.0/internal/db/dump/dump.go)
- [Official backup and restore guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)


Further isolation review found that this CLI version's default data-dump filter
includes cron and net. Production has scheduler and outbound request-queue tables.
Do not restore those operational rows into a running target. Exact proposed scope,
consistency, protected storage, isolation and acceptance steps are recorded in
BACKUP-RESTORE-ISOLATION-REVIEW.md. No row export or restore has been performed.
