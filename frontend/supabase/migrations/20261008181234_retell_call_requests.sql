CREATE TABLE public.retell_call_requests (
  id uuid PRIMARY KEY,
  lead_id uuid NOT NULL REFERENCES public.leads(id),
  requested_by uuid NOT NULL REFERENCES public.profiles(id),
  phone_number text NOT NULL CHECK (phone_number ~ '^\+1[2-9][0-9]{9}$'),
  status text NOT NULL CHECK (status IN ('submitting','accepted','unknown','completed')),
  provider_call_id text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- A lost response must block a new reference for the same recipient too.
CREATE UNIQUE INDEX retell_call_requests_unresolved_phone
ON public.retell_call_requests(phone_number) WHERE status <> 'completed';
CREATE INDEX retell_call_requests_lead ON public.retell_call_requests(lead_id);
CREATE INDEX retell_call_requests_operator ON public.retell_call_requests(requested_by);
ALTER TABLE public.retell_call_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.retell_call_requests FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.retell_call_requests TO service_role;
COMMENT ON TABLE public.retell_call_requests IS
'Server-only call claims. Never replay submitting/unknown calls without provider reconciliation.';
