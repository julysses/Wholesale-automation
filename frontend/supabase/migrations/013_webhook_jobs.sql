-- ─────────────────────────────────────────────────────────────────────────────
-- 013_webhook_jobs.sql — durable async queue for serverless (Vercel) webhooks
--
-- Why: On Vercel the FastAPI function is frozen the instant it returns a
-- response, so FastAPI BackgroundTasks (and any fire-and-forget asyncio task)
-- never finish. Inbound webhooks therefore enqueue a row here and return 200
-- immediately; a Vercel Cron hits POST /webhooks/_worker/drain once a minute to
-- process pending rows by replaying them through the existing handlers.
--
-- Standalone — does NOT depend on migrations 011/012 (RealtyAPI). Safe to apply
-- on its own.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS webhook_jobs (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  source       TEXT        NOT NULL,            -- batchdialer | launch_control | retell | retell_call | air_ai | vapi | facebook
  payload      JSONB       NOT NULL,            -- raw provider payload, replayed by the worker
  status       TEXT        NOT NULL DEFAULT 'pending',  -- pending | processing | done | failed
  attempts     INT         NOT NULL DEFAULT 0,
  last_error   TEXT,
  processed_at TIMESTAMPTZ
);

-- Drain query: oldest pending first.
CREATE INDEX IF NOT EXISTS idx_webhook_jobs_status_created
  ON webhook_jobs (status, created_at);

-- Service-role only. The webhook function authenticates with the Supabase
-- service-role key (which bypasses RLS); enabling RLS with no public policy
-- keeps the queue invisible to anon/authenticated browser clients.
ALTER TABLE webhook_jobs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE webhook_jobs IS
  'Durable queue for inbound provider webhooks under serverless (Vercel) hosting. Drained by POST /webhooks/_worker/drain via Vercel Cron.';
