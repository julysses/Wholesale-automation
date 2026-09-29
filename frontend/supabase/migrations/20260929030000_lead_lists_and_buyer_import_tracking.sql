-- Track which uploaded list each lead/buyer came from so a whole list can be
-- reviewed, re-scored or deleted in one action.

CREATE TABLE IF NOT EXISTS public.lead_lists (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  name        TEXT NOT NULL,
  filename    TEXT,
  row_count   INT NOT NULL DEFAULT 0
);

ALTER TABLE public.lead_lists ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS authenticated_full_access ON public.lead_lists;
CREATE POLICY authenticated_full_access ON public.lead_lists FOR ALL TO authenticated USING (TRUE);
DROP POLICY IF EXISTS require_approved_operator ON public.lead_lists;
CREATE POLICY require_approved_operator ON public.lead_lists AS RESTRICTIVE FOR ALL TO authenticated
  USING ((SELECT public.is_approved())) WITH CHECK ((SELECT public.is_approved()));

-- ON DELETE SET NULL: removing a list record never silently deletes leads;
-- the API deletes the leads explicitly (and skips worked leads by default).
ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS list_id UUID REFERENCES public.lead_lists(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_leads_list_id ON public.leads(list_id);
-- Scoring backlog scan: unscored leads, oldest first.
CREATE INDEX IF NOT EXISTS idx_leads_unscored ON public.leads(created_at) WHERE score_motivation IS NULL;

ALTER TABLE public.buyers
  ADD COLUMN IF NOT EXISTS import_log_id UUID REFERENCES public.buyer_import_log(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_buyers_import_log_id ON public.buyers(import_log_id);
