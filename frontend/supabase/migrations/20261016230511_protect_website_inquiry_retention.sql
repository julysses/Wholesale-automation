-- Keep website inquiries out of imported-list cleanup. Existing permissions are preserved.
CREATE OR REPLACE FUNCTION public.lead_retention_calc(
  l public.leads, p_dupe boolean DEFAULT false,
  OUT o_rule text, OUT o_action text, OUT o_due timestamptz, OUT o_deletable boolean, OUT o_reason text
) LANGUAGE plpgsql STABLE
SET search_path=pg_catalog,public,pg_temp AS $$
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

  -- Distinct website receipts carry consent and follow-up history even when
  -- an address matches an imported record. List cleanup must not erase them.
  IF l.form_submission_id IS NOT NULL
     OR coalesce(l.inbound_channel, '') IN ('web_form', 'web-form')
     OR src IN ('web_form', 'web-form') THEN
    o_rule := 'website_inquiry'; o_action := 'hold'; o_due := NULL;
    o_reason := 'Website inquiry: preserve submission and consent history; review before archive'; RETURN;
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

CREATE OR REPLACE FUNCTION public.lead_retention_row_trigger() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r record;
BEGIN
  SELECT * INTO r FROM public.lead_retention_calc(NEW, false);
  -- keep an existing duplicate verdict until the next full refresh
  IF TG_OP = 'UPDATE' AND OLD.retention_rule = 'duplicates' AND r.o_rule NOT IN ('dnc', 'transaction', 'worked', 'website_inquiry') THEN
    RETURN NEW;
  END IF;
  NEW.retention_rule := r.o_rule; NEW.retention_action := r.o_action; NEW.retention_due_at := r.o_due;
  NEW.retention_deletable := r.o_deletable; NEW.retention_reason := r.o_reason;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS leads_retention ON public.leads;
CREATE TRIGGER leads_retention
  BEFORE INSERT OR UPDATE OF status, contact_attempts, last_contact_date, dnc, source, property_type, form_submission_id, inbound_channel
  ON public.leads FOR EACH ROW EXECUTE FUNCTION public.lead_retention_row_trigger();

-- Repair only the display classifications of existing website inquiries.
-- No source, receipt, task, consent, contact or sending state is changed.
SELECT public.refresh_lead_retention(coalesce(array_agg(id), ARRAY[]::uuid[]))
FROM public.leads
WHERE form_submission_id IS NOT NULL
   OR coalesce(inbound_channel, '') IN ('web_form', 'web-form')
   OR coalesce(source, '') IN ('web_form', 'web-form');
