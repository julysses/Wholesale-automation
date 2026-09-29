-- Application roles may use tables but must not create/shadow public objects.
REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated;

-- Reviewed function bodies use built-ins and public application tables.
-- Search pg_catalog first and temporary objects last.
ALTER FUNCTION public.update_updated_at() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.update_updated_at_column() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.increment_contact_attempts(uuid) SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.notify_hot_lead() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.sync_deal_to_lead() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.update_app_settings_ts() SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.recompute_priority_ranks() SET search_path = pg_catalog, public, pg_temp;

-- Approval lookup is needed by authenticated RLS, not public visitors.
REVOKE EXECUTE ON FUNCTION public.is_approved() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_approved() TO authenticated, service_role;

-- Inquiry submission does not require optional text-message consent.
-- Preserve every other question and its original order.
UPDATE public.lead_form_configs
SET questions = (
  SELECT jsonb_agg(
    CASE WHEN q->>'field_name' = 'sms_opt_in'
      THEN jsonb_set(q, '{required}', 'false'::jsonb)
      ELSE q END ORDER BY position
  ) FROM jsonb_array_elements(questions) WITH ORDINALITY AS fields(q, position)
)
WHERE slug = 'hilltop-home-co'
  AND jsonb_typeof(questions) = 'array';
