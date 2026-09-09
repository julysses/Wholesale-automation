# Deployment and operational release checks

Reviewed September 8, 2026. The committed `vercel.json` serves the React build and
routes both `/api/*` and `/webhooks/*` to `api/index.py` using Vercel's Python
runtime. It does not proxy to Railway. `railway.toml`, `Dockerfile` and `start.sh`
are alternative persistent-host entry points; their presence does not establish
that such a host is deployed.

## Configuration

- Set `SUPABASE_URL` and the server-only `SUPABASE_SERVICE_ROLE_KEY` for the API.
  Browser configuration uses `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`, or
  the equivalent public values from `/api/config`. Never expose the service role
  key through a `VITE_*` variable.
- Set `WEBHOOK_STRICT=true` and configure the secret for each enabled provider.
  Retell verifies its timestamped signature using `RETELL_WEBHOOK_SECRET` when
  provided, otherwise `RETELL_API_KEY`; the configured value must be the API key
  designated by Retell for webhook verification. Facebook needs its app secret
  and verification token. Test callbacks from enabled providers before routing
  real leads. A successful health check does not test these credentials.
- Use `CORS_STRICT=true` with the intended `CORS_ORIGINS` if the browser and API
  use different origins. Inspect the application's existing preview-origin
  allowance before treating CORS as an origin allowlist.
- Set `CRON_SECRET` only if using the authenticated webhook drain endpoint.
  There is no webhook-drain cron schedule in the committed Vercel configuration.

## Schema rollout

`tools/run_migrations.py` requires a PostgreSQL `DATABASE_URL`; `SUPABASE_URL` is
an HTTP endpoint and cannot substitute for it. The runner loads the repository
`.env`, honors existing environment values, and stops startup on a migration
failure. Vercel's Python entry point does not run this script automatically.

The script records applied filenames in `_migrations`, independently of the
Supabase CLI migration history. Before starting it against an existing database,
reconcile the actual schema and both histories; do not blindly replay historical
migrations. Keep migration 011 before 012. Validate changes against a staging
database and follow the project's normal backup and migration rollout process.

`20260909023229_protect_public_intake.sql` removes anonymous INSERT access from
`lead_form_submissions` and `fb_leads`. The supported public submission API uses
the service role after validation and rate limiting. After applying the migration,
verify that direct anonymous database inserts fail and an approved test submission
through the API succeeds. This review created the migration but did not apply it.

Before large imports, inspect the deployed `app.enrich_on_insert` setting and the
011/012 trigger configuration so import volume does not unexpectedly fan out paid
enrichment requests. Reconcile and backfill enrichment deliberately.

## Webhook execution and recovery

Current routes await processing inline before responding. Escaped processing
errors return 503. Request duration and external-provider latency therefore remain
release checks; neither the repository nor a unit test proves that every real
call completes inside the deployed function's duration limit.

Retell completion events require the existing `webhook_jobs` table (migration
013). Event receipt rows retain ended/analyzed payloads. A separate deterministic
call-ID receipt grants one completion attempt across retries and both routes.
An ended callback without usable transcript data defers lead automation. Completed
claims skip repeated side effects; failed or interrupted claims remain parked.

For a failed/processing completion receipt, inspect its `last_error`, call record,
qualification, task and outreach/provider history. Determine which actions already
succeeded, repair only the missing actions, and reconcile the receipt deliberately.
Do not delete the receipt or reset it to pending and assume replay is safe: an
external send may already have succeeded. This prevents duplicate attempts but
does not guarantee delivery or provide automatic recovery.

`/webhooks/_worker/drain` processes pending queue entries only. It does not recover
parked completion claims, and its existence is not evidence that a worker or
scheduler is running. Some other provider handlers still catch failures internally;
acceptance testing and monitoring must cover every integration enabled at launch.

## Required release evidence

Follow `docs/launch-review.md` for the review results and outstanding gates:
approved-account CRUD/browser acceptance, staging migration verification, enabled
provider round trips, duration/recovery checks, and post-deployment smoke tests.
Calendar records currently save locally; external calendar synchronization is
explicitly reported as unavailable and must not be advertised as working.
