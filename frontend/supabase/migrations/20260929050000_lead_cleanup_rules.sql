-- Retention rules: which unworked leads are safe to delete, and when.
-- Only ever selects leads nobody has touched (unworked status, no contact, not DNC).
-- The API deletes the returned ids in chunks; nothing here deletes by itself.

CREATE OR REPLACE FUNCTION public.lead_cleanup_ids(p_rule text)
RETURNS SETOF uuid
LANGUAGE sql STABLE
AS $$
  WITH untouched AS (
    SELECT l.* FROM public.leads l
    WHERE coalesce(l.dnc, false) = false
      AND l.status IN ('new', 'qualified_hot', 'qualified_warm', 'qualified_cold', 'scoring_error')
      AND coalesce(l.contact_attempts, 0) = 0
      AND l.last_contact_date IS NULL
  ),
  dupes AS (
    SELECT id FROM (
      SELECT u.id,
        row_number() OVER (
          PARTITION BY public.lead_street_key(u.property_address), lower(btrim(u.city))
          ORDER BY (u.source IS NOT NULL) DESC, u.total_score DESC, u.created_at ASC, u.id
        ) AS rn
      FROM untouched u
      WHERE public.lead_street_key(u.property_address) ~ '^[0-9]'
        AND coalesce(u.property_type, '') !~* 'business personal|personal property|mineral|utility|inventory'
    ) x WHERE rn > 1
  )
  SELECT u.id FROM untouched u
  WHERE CASE p_rule
    WHEN 'not_real_estate' THEN coalesce(u.property_type, '') ~* 'business personal|personal property|mineral|utility|inventory'
    WHEN 'duplicates'      THEN u.id IN (SELECT id FROM dupes)
    WHEN 'stale_prefor'    THEN coalesce(u.source, '') ~* 'prefor|foreclos' AND u.created_at < now() - interval '60 days'
    WHEN 'stale_cold'      THEN u.status = 'qualified_cold' AND u.created_at < now() - interval '90 days'
    WHEN 'stale_warm'      THEN u.status = 'qualified_warm' AND u.created_at < now() - interval '180 days'
    WHEN 'stale_tax_roll'  THEN coalesce(u.source, '') ~* 'delinq|tax roll|tax_roll' AND u.created_at < now() - interval '365 days'
    ELSE false
  END;
$$;

CREATE OR REPLACE FUNCTION public.lead_cleanup_counts()
RETURNS jsonb
LANGUAGE sql STABLE
AS $$
  SELECT coalesce(jsonb_object_agg(r.rule, (SELECT count(*) FROM public.lead_cleanup_ids(r.rule))), '{}'::jsonb)
  FROM (VALUES ('not_real_estate'), ('duplicates'), ('stale_prefor'), ('stale_cold'), ('stale_warm'), ('stale_tax_roll')) r(rule);
$$;

REVOKE ALL ON FUNCTION public.lead_cleanup_ids(text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.lead_cleanup_counts() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lead_cleanup_ids(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.lead_cleanup_counts() TO service_role;
