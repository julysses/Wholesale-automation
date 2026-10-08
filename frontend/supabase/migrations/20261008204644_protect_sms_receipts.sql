-- Provider receipts may be read by approved operators, but only the backend
-- may claim, reconcile or archive delivery evidence.
ALTER TABLE public.sms_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS authenticated_full_access ON public.sms_events;
CREATE POLICY authenticated_read_sms_events ON public.sms_events
  FOR SELECT TO authenticated USING (true);
-- Preserve the existing restrictive approval policy for reads.
REVOKE ALL ON public.sms_events FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.sms_events TO authenticated;
GRANT SELECT,INSERT,UPDATE ON public.sms_events TO service_role;
REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON public.sms_events FROM service_role;
