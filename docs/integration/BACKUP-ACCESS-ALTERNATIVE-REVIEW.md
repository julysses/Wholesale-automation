# Passwordless backup access alternative — October 23

Owner chose a reviewed alternative because the existing DB password is unavailable.
Review complete for an initial access probe; no login or backup has been created.

## Selected route

Use the existing authenticated Supabase account with the official Management API
POST /v1/projects/{ref}/cli/login-role, explicitly requesting {"read_only":true}.
The inspected CLIv2.79.0 API model supports this field and returns role/password/
ttl_seconds. Its default linked DB path instead requests read_only:false; do not
use that default for this probe. The endpoint is experimental/Beta in current docs.

This creates new database login access, so the exact operation must be approved
before execution. It does not require resetting the project password or purchasing
another project. Existing CLI credentials will be reused solely for api.supabase.com;
no browser token extraction or token output is needed.

## Concrete initial operation

- Request one read-only login on the existing production project. Capture returned
  credentials only in process memory; never print them or save to Git/logs/chat.
- Require a positive bounded ttl_seconds and inspect the returned role's actual
  login expiry, role memberships, table privileges and session read-only state.
  Do not infer non-writing privileges solely from the request flag. Stop if any
  result is unconfirmed or the role can modify application data.
- Make only catalog/permission/connection probes, not customer-table exports,
  migrations, updates, privilege grants or dispatch calls. Close every connection.
- Verify a finite password expiry and retain only non-secret capability results.
  Password expiry prevents new logins, not existing sessions; closing connections
  is required. Do not assume the role record disappears automatically.
- Do not use the API DELETE endpoint as routine cleanup: its documented operation
  removes CLI login roles together and could disrupt unrelated CLI use.
- If read-only access cannot export the required objects completely, report that
  limitation. Do not silently switch to a write-capable login or grant more rights.

## Subsequent backup/recovery boundary

A successful probe establishes access capability only. Before copying production
rows, finish protected local storage, exact export scope/snapshot consistency and
compatible isolated restore execution from BACKUP-RESTORE-ISOLATION-REVIEW.md.
No Vault contents, credentials or runnable outbound jobs/requests may be replayed.
No paid resource, existing restore-project overwrite or production write is part
of this access-probe request. The full backup/restore gate remains open.

Evidence reviewed:
- https://supabase.com/docs/reference/api/v1-create-login-role
- https://supabase.com/docs/guides/troubleshooting/permission-denied-when-deleting-the-cli_login_postgres-role-808bae
- https://github.com/supabase/cli/blob/v2.79.0/pkg/api/types.gen.go
- https://github.com/supabase/cli/blob/v2.79.0/internal/utils/flags/db_url.go
