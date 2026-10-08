-- Exact receipts independently inspected: controlled launch/provider/website fixtures.
-- Do not infer exclusions from arbitrary future names, UTMs or public form fields.
INSERT INTO public.lead_reporting_exclusions(lead_id,reason,recorded_by)
 SELECT DISTINCT s.lead_id,'Confirmed controlled launch fixture; receipt '||s.id::text||'. Raw intake, owner tasks and provider evidence remain intact.','Codex launch verification'
 FROM public.lead_form_submissions s
 WHERE s.processing_status='processed' AND s.lead_id IS NOT NULL AND s.id IN (
 '81a6b3a0-0391-4bcf-b733-9c173cc4cd06','4951f89d-e2f1-4e04-aef5-46322afb5a5c',
 'a67f57ed-b306-4e9b-8f4f-61e19b866587','86ebc536-730b-4486-83fb-565b051ac075',
 '05e83afc-dbaf-4648-9cc7-56796e7c629c','cf68ee58-fad5-4995-ad73-c269b06f8809',
 '94a71914-7a4b-4055-8e77-c60e31956c92','b5989183-c956-4002-b6ea-e56972b40b71',
 '42e8b3cb-0277-4a53-90da-3aef28ec9f06','23b5dd57-6cd9-4516-80d7-6f1c15524eee',
 'df0d1d92-a330-44b5-bbb9-953d24cd7bdd','82116394-8094-4797-a8b5-219a66e31b53',
 'a1081da7-5eb2-48a5-87eb-8e7da0ab3fa6','681d5d7d-8527-4fe4-b420-69e5e77e7116')
 AND NOT EXISTS(SELECT 1 FROM public.lead_reporting_exclusions q WHERE q.lead_id=s.lead_id AND q.revoked_at IS NULL);
CREATE VIEW public.reportable_form_submissions WITH(security_invoker=true) AS
 SELECT s.* FROM public.lead_form_submissions s JOIN public.reportable_leads l ON l.id=s.lead_id WHERE s.processing_status='processed';
REVOKE ALL ON public.reportable_form_submissions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.reportable_form_submissions TO authenticated,service_role;
