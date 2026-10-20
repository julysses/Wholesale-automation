-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261012213446_human_offer_review.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
-- Append-only human offer decisions. No provider dispatch or historical approval backfill.
CREATE SCHEMA offer_review;
REVOKE ALL ON SCHEMA offer_review FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA offer_review TO service_role;
CREATE TABLE offer_review.events (
 id uuid PRIMARY KEY, lead_id uuid NOT NULL REFERENCES public.leads(id),
 operator_id uuid NOT NULL REFERENCES public.profiles(id),
 action text NOT NULL CHECK(action IN ('draft','approve','revoke')),
 expected_version integer NOT NULL CHECK(expected_version>=0),
 revision_id uuid NOT NULL, terms jsonb, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE offer_review.heads (
 lead_id uuid PRIMARY KEY REFERENCES public.leads(id), version integer NOT NULL,
 revision_id uuid NOT NULL REFERENCES offer_review.events(id),
 approval_id uuid REFERENCES offer_review.events(id)
);
ALTER TABLE offer_review.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE offer_review.heads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA offer_review FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON offer_review.events TO service_role;
GRANT SELECT,INSERT,UPDATE ON offer_review.heads TO service_role;
CREATE INDEX offer_review_events_lead ON offer_review.events(lead_id,created_at);

CREATE FUNCTION public.offer_review_snapshot(p_lead uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE h offer_review.heads; r offer_review.events; a offer_review.events;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO h FROM offer_review.heads WHERE lead_id=p_lead;
 IF NOT FOUND THEN RETURN jsonb_build_object('lead_id',p_lead,'version',0,'revision',NULL,'approval',NULL,'approved',false,'outbound_enabled',false); END IF;
 SELECT * INTO r FROM offer_review.events WHERE id=h.revision_id;
 SELECT * INTO a FROM offer_review.events WHERE id=h.approval_id;
 RETURN jsonb_build_object('lead_id',p_lead,'version',h.version,'revision',to_jsonb(r),
  'approval',CASE WHEN a.id IS NULL THEN NULL ELSE to_jsonb(a) END,
  'approved',a.id IS NOT NULL AND (r.terms->>'expires_at')::timestamptz>clock_timestamp(),
  'outbound_enabled',false);
END $$;

CREATE FUNCTION public.record_offer_review(p_id uuid,p_lead uuid,p_operator uuid,p_expected integer,
 p_action text,p_revision uuid,p_terms jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved offer_review.events; h offer_review.heads; r offer_review.events;
 amount numeric; expiry timestamptz; closing date;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
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
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead) THEN RETURN jsonb_build_object('missing',true); END IF;
 SELECT * INTO h FROM offer_review.heads WHERE lead_id=p_lead FOR UPDATE;
 IF coalesce(h.version,0)<>p_expected THEN RETURN jsonb_build_object('conflict',true); END IF;
 IF p_action='draft' THEN
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
  IF p_action='approve' AND (r.terms->>'expires_at')::timestamptz<=clock_timestamp()
  THEN RETURN jsonb_build_object('expired',true); END IF;
 END IF;
 INSERT INTO offer_review.events(id,lead_id,operator_id,action,expected_version,revision_id,terms)
 VALUES(p_id,p_lead,p_operator,p_action,p_expected,p_revision,p_terms) RETURNING * INTO saved;
 IF p_action='draft' THEN
  INSERT INTO offer_review.heads(lead_id,version,revision_id,approval_id) VALUES(p_lead,p_expected+1,p_revision,NULL)
  ON CONFLICT(lead_id) DO UPDATE SET version=excluded.version,revision_id=excluded.revision_id,approval_id=NULL;
 ELSE
  UPDATE offer_review.heads SET version=p_expected+1,approval_id=CASE WHEN p_action='approve' THEN p_id ELSE NULL END WHERE lead_id=p_lead;
 END IF;
 RETURN jsonb_build_object('event',to_jsonb(saved),'current',public.offer_review_snapshot(p_lead,p_operator),'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.offer_review_snapshot(uuid,uuid),public.record_offer_review(uuid,uuid,uuid,integer,text,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.offer_review_snapshot(uuid,uuid),public.record_offer_review(uuid,uuid,uuid,integer,text,uuid,jsonb) TO service_role;
