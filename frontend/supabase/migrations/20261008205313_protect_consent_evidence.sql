-- Intake consent evidence is written only by trusted backend handlers.
ALTER TABLE public.lead_form_submissions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auth_all_lead_form_submissions ON public.lead_form_submissions;
CREATE POLICY authenticated_read_lead_form_submissions ON public.lead_form_submissions
  FOR SELECT TO authenticated USING (true);
REVOKE ALL ON public.lead_form_submissions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.lead_form_submissions TO authenticated;
GRANT SELECT,INSERT,UPDATE ON public.lead_form_submissions TO service_role;
REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.lead_form_submissions FROM service_role;

-- Keep existing recipient-scoped notification policies and allow only read marks
-- from the browser. Metadata includes the native Meta consent receipt.
ALTER TABLE public.app_notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.app_notifications FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.app_notifications TO authenticated;
GRANT UPDATE (read,read_at) ON public.app_notifications TO authenticated;
GRANT SELECT,INSERT,UPDATE ON public.app_notifications TO service_role;
REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.app_notifications FROM service_role;
