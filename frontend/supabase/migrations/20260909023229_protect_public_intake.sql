-- Public forms write through the validated, rate-limited service-role API.
-- Anonymous database inserts bypass that API and must not be allowed.
-- No rows are changed. Existing approved-operator policies are retained.
DROP POLICY IF EXISTS "public_insert_submissions" ON public.lead_form_submissions;
DROP POLICY IF EXISTS "anon_insert_fb_leads" ON public.fb_leads;

REVOKE INSERT ON TABLE public.lead_form_submissions FROM anon;
REVOKE INSERT ON TABLE public.fb_leads FROM anon;
