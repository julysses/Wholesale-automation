-- One retention rule per lead, defined in exactly one place (lead_retention_calc).
-- It drives (a) the per-lead "Keep / Action" column in the app, (b) the Suggested
-- cleanup panel counts and (c) the delete buttons. Enforcement always recomputes from
-- live data; the stored columns are just the display copy and are refreshed by a
-- trigger, after scoring/cleanup and daily.

ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS retention_rule text,
  ADD COLUMN IF NOT EXISTS retention_action text,      -- work | hold | keep
  ADD COLUMN IF NOT EXISTS retention_due_at timestamptz,
  ADD COLUMN IF NOT EXISTS retention_deletable boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS retention_reason text;
CREATE INDEX IF NOT EXISTS idx_leads_retention_due ON public.leads (retention_due_at) WHERE retention_deletable;

CREATE OR REPLACE FUNCTION public.lead_retention_calc(
  l public.leads, p_dupe boolean DEFAULT false,
  OUT o_rule text, OUT o_action text, OUT o_due timestamptz, OUT o_deletable boolean, OUT o_reason text
) LANGUAGE plpgsql STABLE AS $$
DECLARE
  base timestamptz := coalesce(l.created_at, now());
  src text := coalesce(l.source, '');
  untouched boolean;
  d_prefor timestamptz; d_tier timestamptz; d_tax timestamptz;
  tier_rule text;
BEGIN
  o_deletable := false;
  IF coalesce(l.dnc, false) THEN
    o_rule := 'dnc'; o_action := 'keep';
    o_reason := 'DNC / opted out: keep permanently as your suppression record'; RETURN;
  END IF;
  IF coalesce(l.status, '') IN ('appointment_set', 'offer_made', 'under_contract') THEN
    o_rule := 'transaction'; o_action := 'keep'; o_due := base + interval '7 years';
    o_reason := 'Appointment / offer / contract: keep records 7 years'; RETURN;
  END IF;

  untouched := coalesce(l.status, 'new') IN ('new', 'qualified_hot', 'qualified_warm', 'qualified_cold', 'scoring_error')
               AND coalesce(l.contact_attempts, 0) = 0 AND l.last_contact_date IS NULL;
  IF NOT untouched THEN
    o_rule := 'worked'; o_action := 'hold';
    o_due := coalesce(l.last_contact_date::timestamptz, l.updated_at, base) + interval '12 months';
    o_reason := 'Contacted: hold 12 months from last contact, then archive if no reply'; RETURN;
  END IF;

  o_deletable := true;
  IF coalesce(l.property_type, '') ~* 'business personal|personal property|mineral|utility|inventory' THEN
    o_rule := 'not_real_estate'; o_action := 'hold'; o_due := base;
    o_reason := 'Not real estate (business/personal property record): delete now'; RETURN;
  END IF;
  IF p_dupe THEN
    o_rule := 'duplicates'; o_action := 'hold'; o_due := base;
    o_reason := 'Duplicate of a better-scored copy of this property: delete now'; RETURN;
  END IF;

  -- Earliest of the time-based rules wins, so every lead has exactly one rule.
  d_prefor := CASE WHEN src ~* 'prefor|foreclos' THEN base + interval '60 days' END;
  d_tier := CASE l.status
              WHEN 'qualified_cold' THEN base + interval '90 days'
              WHEN 'qualified_warm' THEN base + interval '180 days' END;
  tier_rule := CASE l.status WHEN 'qualified_cold' THEN 'stale_cold' WHEN 'qualified_warm' THEN 'stale_warm' END;
  d_tax := CASE WHEN src ~* 'delinq|tax roll|tax_roll' THEN base + interval '365 days' END;

  o_due := least(d_prefor, d_tier, d_tax);
  IF o_due IS NULL THEN
    o_rule := 'work'; o_deletable := false; o_action := 'work';
    o_reason := 'Call within 48 hours'; RETURN;
  END IF;
  o_rule := CASE o_due WHEN d_prefor THEN 'stale_prefor' WHEN d_tier THEN tier_rule ELSE 'stale_tax_roll' END;
  o_action := CASE WHEN l.status IN ('qualified_hot', 'qualified_warm', 'new') THEN 'work' ELSE 'hold' END;
  o_reason := CASE o_rule
    WHEN 'stale_prefor'   THEN 'Pre-foreclosure list ages fast: work or re-pull within 60 days, then delete'
    WHEN 'stale_cold'     THEN 'No distress evidence: delete after 90 days if never contacted'
    WHEN 'stale_warm'     THEN 'Warm but never contacted: delete after 180 days'
    ELSE                       'Delinquent tax roll is republished yearly: replace after 12 months' END;
END;
$$;

-- Duplicate losers among untouched real-estate leads (keep the copy with a source and the best score).
CREATE OR REPLACE FUNCTION public.lead_duplicate_losers()
RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
  SELECT id FROM (
    SELECT u.id,
      row_number() OVER (
        PARTITION BY public.lead_street_key(u.property_address), lower(btrim(u.city))
        ORDER BY (u.source IS NOT NULL) DESC, u.total_score DESC, u.created_at ASC, u.id
      ) AS rn
    FROM public.leads u
    WHERE coalesce(u.dnc, false) = false
      AND coalesce(u.status, 'new') IN ('new', 'qualified_hot', 'qualified_warm', 'qualified_cold', 'scoring_error')
      AND coalesce(u.contact_attempts, 0) = 0 AND u.last_contact_date IS NULL
      AND public.lead_street_key(u.property_address) ~ '^[0-9]'
      AND coalesce(u.property_type, '') !~* 'business personal|personal property|mineral|utility|inventory'
  ) x WHERE rn > 1;
$$;

-- Stored display copy. Safe to run any time; only writes rows whose values changed.
CREATE OR REPLACE FUNCTION public.refresh_lead_retention(p_ids uuid[] DEFAULT NULL)
RETURNS int LANGUAGE plpgsql
SET statement_timeout = '120s'
AS $$
DECLARE n int;
BEGIN
  WITH dupes AS MATERIALIZED (SELECT d AS id FROM public.lead_duplicate_losers() d),
  calc AS MATERIALIZED (
    SELECT l.id, r.*
    FROM public.leads l
    CROSS JOIN LATERAL public.lead_retention_calc(l, l.id IN (SELECT id FROM dupes)) r
    WHERE p_ids IS NULL OR l.id = ANY (p_ids)
  ),
  upd AS (
    UPDATE public.leads l SET
      retention_rule = c.o_rule, retention_action = c.o_action, retention_due_at = c.o_due,
      retention_deletable = c.o_deletable, retention_reason = c.o_reason
    FROM calc c
    WHERE l.id = c.id
      AND (l.retention_rule, l.retention_action, l.retention_due_at, l.retention_deletable, l.retention_reason)
          IS DISTINCT FROM (c.o_rule, c.o_action, c.o_due, c.o_deletable, c.o_reason)
    RETURNING 1
  )
  SELECT count(*) INTO n FROM upd;
  RETURN n;
END;
$$;

-- Row-level refresh so a status change in the app updates the label immediately.
CREATE OR REPLACE FUNCTION public.lead_retention_row_trigger() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  SELECT * INTO r FROM public.lead_retention_calc(NEW, false);
  -- keep an existing duplicate verdict until the next full refresh
  IF TG_OP = 'UPDATE' AND OLD.retention_rule = 'duplicates' AND r.o_rule NOT IN ('dnc', 'transaction', 'worked') THEN
    RETURN NEW;
  END IF;
  NEW.retention_rule := r.o_rule; NEW.retention_action := r.o_action; NEW.retention_due_at := r.o_due;
  NEW.retention_deletable := r.o_deletable; NEW.retention_reason := r.o_reason;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS leads_retention ON public.leads;
CREATE TRIGGER leads_retention
  BEFORE INSERT OR UPDATE OF status, contact_attempts, last_contact_date, dnc, source, property_type
  ON public.leads FOR EACH ROW EXECUTE FUNCTION public.lead_retention_row_trigger();

-- Cleanup ids come from the SAME function, live: due, deletable, and matching the rule.
CREATE OR REPLACE FUNCTION public.lead_cleanup_ids(p_rule text)
RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
  WITH dupes AS MATERIALIZED (SELECT d AS id FROM public.lead_duplicate_losers() d)
  SELECT l.id FROM public.leads l
  CROSS JOIN LATERAL public.lead_retention_calc(l, l.id IN (SELECT id FROM dupes)) r
  WHERE r.o_deletable AND r.o_rule = p_rule AND r.o_due <= now();
$$;

CREATE OR REPLACE FUNCTION public.lead_cleanup_counts()
RETURNS jsonb LANGUAGE sql STABLE AS $$
  WITH dupes AS MATERIALIZED (SELECT d AS id FROM public.lead_duplicate_losers() d)
  SELECT coalesce(jsonb_object_agg(rule, n), '{}'::jsonb) FROM (
    SELECT r.o_rule AS rule, count(*) AS n
    FROM public.leads l
    CROSS JOIN LATERAL public.lead_retention_calc(l, l.id IN (SELECT id FROM dupes)) r
    WHERE r.o_deletable AND r.o_due <= now()
    GROUP BY 1
  ) x;
$$;

REVOKE ALL ON FUNCTION public.lead_cleanup_ids(text), public.lead_cleanup_counts(),
  public.refresh_lead_retention(uuid[]), public.lead_duplicate_losers() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lead_cleanup_ids(text), public.lead_cleanup_counts(),
  public.refresh_lead_retention(uuid[]), public.lead_duplicate_losers() TO service_role;

-- Daily refresh so "delete after" dates roll over without anyone opening the app.
CREATE EXTENSION IF NOT EXISTS pg_cron;
SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname = 'refresh-lead-retention';
SELECT cron.schedule('refresh-lead-retention', '15 9 * * *', $cron$SELECT public.refresh_lead_retention()$cron$);
