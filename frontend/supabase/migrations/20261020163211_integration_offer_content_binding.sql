-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261013035456_offer_content_binding.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
-- Freeze review content at draft creation. No historical approval backfill or dispatch.
CREATE TABLE offer_review.content (
 revision_id uuid PRIMARY KEY REFERENCES offer_review.events(id),
 property_snapshot jsonb NOT NULL,
 renderer_version text NOT NULL CHECK(renderer_version='offer-summary-v1'),
 subject text NOT NULL, body text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE offer_review.content ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON offer_review.content FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON offer_review.content TO service_role;
CREATE FUNCTION offer_review.property_snapshot(p_lead uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object('property_address',l.property_address,'city',l.city,
   'state',l.state,'zip_code',l.zip_code) FROM public.leads l WHERE l.id=p_lead
$$;
REVOKE ALL ON FUNCTION offer_review.property_snapshot(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION offer_review.property_snapshot(uuid) TO service_role;
CREATE OR REPLACE FUNCTION public.offer_review_snapshot(p_lead uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE h offer_review.heads; r offer_review.events; a offer_review.events; c offer_review.content; binding_valid boolean;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO h FROM offer_review.heads WHERE lead_id=p_lead;
 IF NOT FOUND THEN RETURN jsonb_build_object('lead_id',p_lead,'version',0,'revision',NULL,'approval',NULL,'approved',false,'outbound_enabled',false,'content',NULL,'binding_valid',false); END IF;
 SELECT * INTO r FROM offer_review.events WHERE id=h.revision_id;
 SELECT * INTO a FROM offer_review.events WHERE id=h.approval_id;
 SELECT * INTO c FROM offer_review.content WHERE revision_id=h.revision_id;
 binding_valid:=c.revision_id IS NOT NULL AND c.property_snapshot IS NOT DISTINCT FROM offer_review.property_snapshot(p_lead);
 RETURN jsonb_build_object('lead_id',p_lead,'version',h.version,'revision',to_jsonb(r),
  'approval',CASE WHEN a.id IS NULL THEN NULL ELSE to_jsonb(a) END,
  'content',CASE WHEN c.revision_id IS NULL THEN NULL ELSE to_jsonb(c) END,'binding_valid',binding_valid,
  'approved',binding_valid AND a.id IS NOT NULL AND (r.terms->>'expires_at')::timestamptz>clock_timestamp(),
  'outbound_enabled',false);
END $$;

CREATE FUNCTION public.record_offer_review_v2(p_id uuid,p_lead uuid,p_operator uuid,p_expected integer,
 p_action text,p_revision uuid,p_terms jsonb,p_reviewed_content uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved offer_review.events; h offer_review.heads; r offer_review.events;
 amount numeric; expiry timestamptz; closing date; property jsonb; address text; message_body text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF (p_action='approve' AND p_reviewed_content IS DISTINCT FROM p_revision) OR (p_action<>'approve' AND p_reviewed_content IS NOT NULL)
 THEN RETURN jsonb_build_object('invalid',true); END IF;
 IF p_id IS NULL OR p_lead IS NULL OR p_expected IS NULL OR p_expected<0 OR p_action IS NULL OR p_action NOT IN ('draft','approve','revoke') OR p_revision IS NULL
 THEN RETURN jsonb_build_object('invalid',true); END IF;
 -- Lock event identity as well as lead identity: conflicting cross-lead replay fails safely.
 PERFORM pg_advisory_xact_lock(hashtextextended('offer-event:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('offer-lead:'||p_lead::text,0));
 SELECT * INTO saved FROM offer_review.events WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id IS DISTINCT FROM p_lead OR saved.operator_id IS DISTINCT FROM p_operator OR saved.action IS DISTINCT FROM p_action
   OR saved.expected_version IS DISTINCT FROM p_expected OR saved.revision_id IS DISTINCT FROM p_revision OR saved.terms IS DISTINCT FROM p_terms
  THEN RETURN jsonb_build_object('conflict',true); END IF;
  RETURN jsonb_build_object('event',to_jsonb(saved),'current',public.offer_review_snapshot(p_lead,p_operator),'replayed',true);
 END IF;
 PERFORM 1 FROM public.leads WHERE id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('missing',true); END IF;
 property:=offer_review.property_snapshot(p_lead);
 SELECT * INTO h FROM offer_review.heads WHERE lead_id=p_lead FOR UPDATE;
 IF coalesce(h.version,0)<>p_expected THEN RETURN jsonb_build_object('conflict',true); END IF;
 IF p_action='draft' THEN
  IF coalesce(length(trim(property->>'property_address')),0)=0 OR coalesce(length(trim(property->>'city')),0)=0
  THEN RETURN jsonb_build_object('invalid',true); END IF;
  IF p_revision<>p_id OR jsonb_typeof(p_terms) IS DISTINCT FROM 'object'
    OR NOT (p_terms ?& ARRAY['price','closing_date','expires_at','recipient','channel','conditions'])
    OR jsonb_typeof(p_terms->'recipient') IS DISTINCT FROM 'string'
    OR jsonb_typeof(p_terms->'conditions') IS DISTINCT FROM 'string'
    OR jsonb_typeof(p_terms->'channel') IS DISTINCT FROM 'string'
    OR (p_terms - ARRAY['price','closing_date','expires_at','recipient','channel','conditions']) <> '{}'::jsonb
  THEN RETURN jsonb_build_object('invalid',true); END IF;
  BEGIN
   amount:=(p_terms->>'price')::numeric; expiry:=(p_terms->>'expires_at')::timestamptz; closing:=(p_terms->>'closing_date')::date;
  EXCEPTION WHEN OTHERS THEN RETURN jsonb_build_object('invalid',true); END;
  IF amount IS NULL OR amount<=0 OR amount>100000000 OR amount<>round(amount,2)
    OR expiry IS NULL OR NOT isfinite(expiry) OR expiry<=clock_timestamp()
    OR closing IS NULL OR NOT isfinite(closing) OR closing<(clock_timestamp() AT TIME ZONE 'America/Chicago')::date
    OR coalesce(p_terms->>'channel','') NOT IN ('manual','email','sms')
    OR coalesce(length(trim(p_terms->>'recipient')),0) NOT BETWEEN 1 AND 320
    OR coalesce(length(trim(p_terms->>'conditions')),0) NOT BETWEEN 1 AND 10000
    OR (p_terms->>'channel'='sms' AND (p_terms->>'recipient') !~ '^\+[1-9][0-9]{7,14}$')
    OR (p_terms->>'channel'='email' AND (p_terms->>'recipient') !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')
  THEN RETURN jsonb_build_object('invalid',true); END IF;
 ELSE
  IF p_terms IS NOT NULL OR h.revision_id IS DISTINCT FROM p_revision THEN RETURN jsonb_build_object('conflict',true); END IF;
  SELECT * INTO r FROM offer_review.events WHERE id=h.revision_id;
  IF p_action='approve' AND NOT EXISTS(SELECT 1 FROM offer_review.content WHERE revision_id=h.revision_id AND property_snapshot=property)
  THEN RETURN jsonb_build_object('conflict',true,'reason','Save a new revision for the current property and content'); END IF;
  IF p_action='approve' AND (r.terms->>'expires_at')::timestamptz<=clock_timestamp()
  THEN RETURN jsonb_build_object('expired',true); END IF;
 END IF;
 INSERT INTO offer_review.events(id,lead_id,operator_id,action,expected_version,revision_id,terms)
 VALUES(p_id,p_lead,p_operator,p_action,p_expected,p_revision,p_terms) RETURNING * INTO saved;
 IF p_action='draft' THEN
  address:=concat_ws(', ',property->>'property_address',property->>'city',property->>'state',property->>'zip_code');
  message_body:='Hilltop Home Co.'||E'\nProperty: '||address||E'\nOffer price: $'||to_char(amount,'FM999999990.00')
   ||E'\nClosing date: '||(p_terms->>'closing_date')||E'\nExpires: '||(p_terms->>'expires_at')
   ||E'\nConditions:\n'||(p_terms->>'conditions');
  INSERT INTO offer_review.content(revision_id,property_snapshot,renderer_version,subject,body)
  VALUES(p_revision,property,'offer-summary-v1','Offer terms for '||address,message_body);
  INSERT INTO offer_review.heads(lead_id,version,revision_id,approval_id) VALUES(p_lead,p_expected+1,p_revision,NULL)
  ON CONFLICT(lead_id) DO UPDATE SET version=excluded.version,revision_id=excluded.revision_id,approval_id=NULL;
 ELSE
  UPDATE offer_review.heads SET version=p_expected+1,approval_id=CASE WHEN p_action='approve' THEN p_id ELSE NULL END WHERE lead_id=p_lead;
 END IF;
 RETURN jsonb_build_object('event',to_jsonb(saved),'current',public.offer_review_snapshot(p_lead,p_operator),'replayed',false);
END $$;

-- Old clients cannot approve content they did not display. Upgrade API and UI together.
REVOKE EXECUTE ON FUNCTION public.record_offer_review(uuid,uuid,uuid,integer,text,uuid,jsonb) FROM service_role;
REVOKE ALL ON FUNCTION public.record_offer_review_v2(uuid,uuid,uuid,integer,text,uuid,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_offer_review_v2(uuid,uuid,uuid,integer,text,uuid,jsonb,uuid) TO service_role;
