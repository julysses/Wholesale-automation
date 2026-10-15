-- Preserve unknown owners; routing to underwriting is not seller outreach.
ALTER TABLE public.land_leads ALTER COLUMN owner_name DROP NOT NULL;
GRANT SELECT,INSERT,UPDATE ON public.land_leads TO service_role;
GRANT SELECT,INSERT ON public.tasks TO service_role;
CREATE TABLE wholesale_ingest.lot_reviews (
 id uuid PRIMARY KEY,lead_id uuid NOT NULL REFERENCES public.leads(id),operator_id uuid NOT NULL REFERENCES public.profiles(id),
 input_hash text NOT NULL,property_snapshot jsonb NOT NULL,is_vacant_lot boolean NOT NULL,
 evidence_url text NOT NULL,notes text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE wholesale_ingest.lot_handoffs (
 id uuid PRIMARY KEY,lead_id uuid NOT NULL UNIQUE REFERENCES public.leads(id),evaluation_id uuid NOT NULL REFERENCES wholesale_ingest.lead_evaluations(id),
 review_id uuid NOT NULL REFERENCES wholesale_ingest.lot_reviews(id),operator_id uuid NOT NULL REFERENCES public.profiles(id),
 assigned_to uuid NOT NULL REFERENCES public.profiles(id),land_lead_id uuid NOT NULL REFERENCES public.land_leads(id),task_id uuid NOT NULL REFERENCES public.tasks(id),
 input_hash text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 acknowledged_by uuid REFERENCES public.profiles(id),acknowledged_at timestamptz
);
ALTER TABLE wholesale_ingest.lot_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE wholesale_ingest.lot_handoffs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.lot_reviews,wholesale_ingest.lot_handoffs FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT ON wholesale_ingest.lot_reviews TO service_role;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.lot_handoffs TO service_role;
CREATE FUNCTION public.review_list_lot(p_id uuid,p_operator uuid,p_lead uuid,p_input_hash text,p_is_lot boolean,p_evidence text,p_notes text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE existing wholesale_ingest.lot_reviews; snapshot jsonb; property wholesale_ingest.properties;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_lead IS NULL OR p_is_lot IS NULL OR coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$'
 OR coalesce(p_evidence,'') !~ '^https://[^[:space:]]+$' OR length(p_evidence)>2000 OR coalesce(length(trim(p_notes)),0) NOT BETWEEN 1 AND 2000 THEN RETURN jsonb_build_object('blocked','invalid_review'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('lot-review:'||p_id::text,0));
 SELECT * INTO existing FROM wholesale_ingest.lot_reviews WHERE id=p_id;
 IF FOUND THEN
  IF existing.lead_id<>p_lead OR existing.operator_id<>p_operator OR existing.input_hash<>p_input_hash OR existing.is_vacant_lot<>p_is_lot OR existing.evidence_url<>p_evidence OR existing.notes<>p_notes THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('review',to_jsonb(existing),'replayed',true);
 END IF;
 SELECT * INTO property FROM wholesale_ingest.properties WHERE lead_id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','property_unverified'); END IF;
 snapshot:=public.list_scoring_input(p_lead);
 IF snapshot->>'input_hash' IS DISTINCT FROM p_input_hash THEN RETURN jsonb_build_object('blocked','stale_input'); END IF;
 UPDATE wholesale_ingest.properties SET is_vacant_lot=p_is_lot WHERE id=property.id;
 INSERT INTO wholesale_ingest.lot_reviews(id,lead_id,operator_id,input_hash,property_snapshot,is_vacant_lot,evidence_url,notes)
 VALUES(p_id,p_lead,p_operator,p_input_hash,to_jsonb(property)-'is_vacant_lot',p_is_lot,p_evidence,p_notes) RETURNING * INTO existing;
 RETURN jsonb_build_object('review',to_jsonb(existing),'replayed',false);
END $$;
CREATE FUNCTION public.handoff_list_lot(p_id uuid,p_operator uuid,p_evaluation uuid,p_assignee uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE evaluation wholesale_ingest.lead_evaluations; review wholesale_ingest.lot_reviews; property wholesale_ingest.properties;
 saved wholesale_ingest.lot_handoffs; land public.land_leads; task uuid; snapshot jsonb; matches integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_evaluation IS NULL OR p_assignee IS NULL THEN RETURN jsonb_build_object('blocked','invalid_handoff'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('lot-handoff:'||p_id::text,0));
 SELECT * INTO saved FROM wholesale_ingest.lot_handoffs WHERE id=p_id;
 IF FOUND THEN
  IF saved.operator_id<>p_operator OR saved.evaluation_id<>p_evaluation OR saved.assigned_to<>p_assignee THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('handoff',to_jsonb(saved),'replayed',true,'outreach_authorized',false);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_assignee AND status='approved') THEN RETURN jsonb_build_object('blocked','assignee_unavailable'); END IF;
 SELECT * INTO evaluation FROM wholesale_ingest.lead_evaluations WHERE id=p_evaluation;
 IF NOT FOUND OR evaluation.route<>'underwrite_lot' OR evaluation.input_snapshot IS NULL OR evaluation.prompt_version<>'daily-list-score-v1' THEN RETURN jsonb_build_object('blocked','qualifying_score_required'); END IF;
 SELECT * INTO property FROM wholesale_ingest.properties WHERE lead_id=evaluation.lead_id FOR UPDATE;
 IF NOT FOUND OR property.is_vacant_lot IS DISTINCT FROM true THEN RETURN jsonb_build_object('blocked','verified_lot_required'); END IF;
 SELECT * INTO saved FROM wholesale_ingest.lot_handoffs WHERE lead_id=evaluation.lead_id;
 IF FOUND THEN RETURN jsonb_build_object('blocked','existing_handoff','handoff',to_jsonb(saved)); END IF;
 snapshot:=public.list_scoring_input(evaluation.lead_id);
 IF snapshot->>'input_hash' IS DISTINCT FROM evaluation.input_hash THEN RETURN jsonb_build_object('blocked','stale_score'); END IF;
 SELECT * INTO review FROM wholesale_ingest.lot_reviews WHERE lead_id=evaluation.lead_id ORDER BY created_at DESC,id DESC LIMIT 1;
 IF NOT FOUND OR NOT review.is_vacant_lot OR review.property_snapshot IS DISTINCT FROM (to_jsonb(property)-'is_vacant_lot') THEN RETURN jsonb_build_object('blocked','lot_review_required'); END IF;
 IF nullif(trim(property.address_std),'') IS NULL OR nullif(trim(property.city),'') IS NULL OR nullif(trim(property.unit),'') IS NOT NULL THEN RETURN jsonb_build_object('blocked','land_identity_review_required'); END IF;
 -- Serialize cooperating handoffs and legacy land writers during deduplication.
 LOCK TABLE public.land_leads IN SHARE ROW EXCLUSIVE MODE;
 SELECT count(*) INTO matches FROM public.land_leads WHERE lead_id=evaluation.lead_id;
 IF matches>1 THEN RETURN jsonb_build_object('blocked','land_identity_conflict'); END IF;
 IF matches=1 THEN
  SELECT * INTO land FROM public.land_leads WHERE lead_id=evaluation.lead_id;
  IF land.state IS DISTINCT FROM property.state OR land.county IS DISTINCT FROM property.county
   OR lower(trim(land.property_address)) IS DISTINCT FROM lower(trim(property.address_std))
   OR lower(trim(land.city)) IS DISTINCT FROM lower(trim(property.city))
   OR (property.parcel_id IS NOT NULL AND land.apn IS DISTINCT FROM property.parcel_id)
   OR land.status='dead' THEN RETURN jsonb_build_object('blocked','land_identity_conflict'); END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM public.land_leads l WHERE
   (lower(trim(l.property_address))=lower(trim(property.address_std)) AND lower(trim(l.city))=lower(trim(property.city)))
   OR (l.state=property.state AND l.county=property.county AND property.parcel_id IS NOT NULL AND l.apn=property.parcel_id))
   THEN RETURN jsonb_build_object('blocked','legacy_land_match_requires_review'); END IF;
  INSERT INTO public.land_leads(lead_id,source,owner_name,property_address,city,state,zip_code,county,apn,status,assigned_to,sms_sequence_active)
  VALUES(evaluation.lead_id,'daily_lists',NULL,property.address_std,property.city,property.state,property.zip,property.county,property.parcel_id,'new',p_assignee,false) RETURNING * INTO land;
 END IF;
 task:=gen_random_uuid();
 INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
 VALUES(task,'Review lot underwriting intake','Verified list lot. Land record '||land.id::text||'; scoring evidence '||evaluation.id::text||'. Acknowledge receipt in land underwriting. Verify ownership, zoning, utilities and buildability; no offer or contact permission granted.','pending','high','follow_up',p_assignee,now());
 INSERT INTO wholesale_ingest.lot_handoffs(id,lead_id,evaluation_id,review_id,operator_id,assigned_to,land_lead_id,task_id,input_hash)
 VALUES(p_id,evaluation.lead_id,evaluation.id,review.id,p_operator,p_assignee,land.id,task,evaluation.input_hash) RETURNING * INTO saved;
 RETURN jsonb_build_object('handoff',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.acknowledge_list_lot(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.lot_handoffs;
BEGIN
 SELECT * INTO saved FROM wholesale_ingest.lot_handoffs WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','handoff_missing'); END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND (id=saved.assigned_to OR role='admin')) THEN RAISE EXCEPTION 'Assigned operator or approved administrator required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.land_leads WHERE id=saved.land_lead_id AND lead_id=saved.lead_id) THEN RETURN jsonb_build_object('blocked','destination_changed'); END IF;
 IF saved.acknowledged_at IS NOT NULL THEN RETURN jsonb_build_object('handoff',to_jsonb(saved),'replayed',true,'outreach_authorized',false); END IF;
 UPDATE wholesale_ingest.lot_handoffs SET acknowledged_by=p_operator,acknowledged_at=clock_timestamp() WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('handoff',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.list_lot_handoffs(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE admin boolean;
BEGIN
 SELECT role='admin' INTO admin FROM public.profiles WHERE id=p_operator AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('count',(SELECT count(*) FROM wholesale_ingest.lot_handoffs WHERE admin OR assigned_to=p_operator),
 'handoffs',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.created_at DESC,h.id DESC),'[]') FROM (
 SELECT h.*,p.address_std,p.county,coalesce(h.input_hash=public.list_scoring_input(h.lead_id)->>'input_hash',false) AS current
 FROM wholesale_ingest.lot_handoffs h JOIN wholesale_ingest.properties p ON p.lead_id=h.lead_id
 WHERE admin OR h.assigned_to=p_operator ORDER BY h.created_at DESC,h.id DESC LIMIT 50 OFFSET p_offset) h));
END $$;
CREATE FUNCTION wholesale_ingest.guard_lot_handoff() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['acknowledged_by','acknowledged_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['acknowledged_by','acknowledged_at'])
 OR (OLD.acknowledged_at IS NOT NULL AND (NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at OR NEW.acknowledged_by IS DISTINCT FROM OLD.acknowledged_by))
 OR (NEW.acknowledged_at IS NULL) IS DISTINCT FROM (NEW.acknowledged_by IS NULL) THEN RAISE EXCEPTION 'Immutable lot handoff'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_lot_handoff BEFORE UPDATE ON wholesale_ingest.lot_handoffs FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.guard_lot_handoff();
REVOKE ALL ON FUNCTION public.review_list_lot(uuid,uuid,uuid,text,boolean,text,text),public.handoff_list_lot(uuid,uuid,uuid,uuid),public.acknowledge_list_lot(uuid,uuid),public.list_lot_handoffs(uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_list_lot(uuid,uuid,uuid,text,boolean,text,text),public.handoff_list_lot(uuid,uuid,uuid,uuid),public.acknowledge_list_lot(uuid,uuid),public.list_lot_handoffs(uuid,integer) TO service_role;

CREATE FUNCTION public.list_lot_candidates(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('count',(SELECT count(*) FROM wholesale_ingest.properties WHERE lead_id IS NOT NULL),
 'candidates',(SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.created_at,c.id),'[]') FROM (
 SELECT p.id,p.lead_id,p.address_std,p.city,p.county,p.parcel_id,p.is_vacant_lot,p.created_at,
 s.value->>'input_hash' AS input_hash,s.value->>'blocked' AS blocked,e.id AS evaluation_id,e.route,
 coalesce(e.input_hash=s.value->>'input_hash',false) AS score_current
 FROM (SELECT * FROM wholesale_ingest.properties WHERE lead_id IS NOT NULL ORDER BY created_at,id LIMIT 50 OFFSET p_offset) p
 CROSS JOIN LATERAL (SELECT public.list_scoring_input(p.lead_id) value) s
 LEFT JOIN LATERAL (SELECT id,route,input_hash FROM wholesale_ingest.lead_evaluations WHERE lead_id=p.lead_id AND input_snapshot IS NOT NULL ORDER BY created_at DESC,id DESC LIMIT 1) e ON true
 ) c));
END $$;
REVOKE ALL ON FUNCTION public.list_lot_candidates(uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_lot_candidates(uuid,integer) TO service_role;
