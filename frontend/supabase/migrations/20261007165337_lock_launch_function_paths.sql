-- Reviewed launch functions: preserve public table resolution, prefer built-ins,
-- and prevent session-controlled schemas from changing name resolution.
ALTER FUNCTION public.recompute_priority_ranks() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_street_key(text) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.score_leads_rules(uuid[],uuid,boolean,boolean) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_cleanup_ids(text) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_cleanup_counts() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_retention_calc(public.leads,boolean) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_duplicate_losers() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.refresh_lead_retention(uuid[]) SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION public.lead_retention_row_trigger() SET search_path=pg_catalog,public,pg_temp;
