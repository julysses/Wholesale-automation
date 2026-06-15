# Deployment — Vercel (frontend) + persistent backend host

WholesaleOS uses a **hybrid** deployment. The React SPA is served by **Vercel**;
the FastAPI backend (webhooks + AI agents + background tasks) runs on a
**persistent host** (Railway is preconfigured via `railway.toml` / `Dockerfile`);
Supabase provides Postgres + Edge Functions + `pg_cron`.

## Why not 100% on Vercel?

Vercel serverless functions are terminated when the HTTP response returns and have
a 60–300s max duration. This breaks two things the app depends on:

- **Webhook background work** — `web/api/webhooks.py` responds `200` immediately, then
  finishes qualification/HOT-lead automation in FastAPI `BackgroundTasks` /
  `asyncio.create_task`. On serverless that work is killed mid-flight.
- **Long agent pipelines** — `orchestrator/master_orchestrator.py` `run_full_pipeline`
  is a minutes-long blocking chain that exceeds serverless limits.

So the backend stays on an always-on host. Vercel hosts the SPA and proxies `/api/*`
to that host via `vercel.json` rewrites (keeps the SPA's same-origin relative
`fetch('/api/...')` calls working with no code change).

## Topology

```
Browser ─► Vercel SPA ──/api/* rewrite──► Railway FastAPI ──► Supabase Postgres
Providers ─webhooks (point DIRECTLY at Railway)──────────► Railway FastAPI
Supabase pg_cron/pg_net ─► Edge Functions (PR #1 enrichment/ARV) ─► Postgres
```

## Steps

1. **Deploy the backend** (Railway): it builds from the repo `Dockerfile` / `railway.toml`.
   Set all env vars from `.env.example` (Anthropic, Supabase service-role, every
   `*_WEBHOOK_SECRET`, provider keys). Use the Supabase **pooled Postgres**
   `DATABASE_URL`, not SQLite. Note the public URL, e.g. `https://wholesaleos-api.up.railway.app`.

2. **Configure `vercel.json`**: replace `REPLACE_WITH_BACKEND_HOST` (two places) with the
   Railway host. Commit.

3. **Deploy the frontend** (Vercel): import the repo. Build settings come from `vercel.json`.
   Set Vercel env vars `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. Deploy a
   preview, smoke-test, then promote to production.

4. **Point webhook providers directly at the backend host** (NOT through Vercel) so signed
   request bodies are byte-preserved:
   - Retell: `https://<backend>/webhooks/retell`
   - VAPI: `https://<backend>/webhooks/vapi`
   - BatchDialer: `https://<backend>/webhooks/batchdialer/call`
   - Launch Control: `https://<backend>/webhooks/launch_control/reply`
   - Facebook Lead Ads: `https://<backend>/webhooks/facebook/lead`

5. **Lock down CORS**: set `CORS_STRICT=true` and `CORS_ORIGINS=https://<your-vercel-domain>`
   on the backend. `*.vercel.app` preview domains are allowed automatically.

6. **Supabase / PR #1**: apply migrations (incl. `011_realtyapi_integration.sql`) and deploy
   the Edge Functions; set `REALTYAPI_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY` as Functions secrets. Enable `pg_net` + `pg_cron`.
