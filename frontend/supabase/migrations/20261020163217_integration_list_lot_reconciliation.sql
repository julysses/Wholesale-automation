-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261013025354_list_lot_reconciliation.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
CREATE TABLE wholesale_ingest.lot_reconciliations (
 id uuid PRIMARY KEY,handoff_id uuid NOT NULL REFERENCES wholesale_ingest.lot_handoffs(id),
 version integer NOT NULL CHECK(version>0),operator_id uuid NOT NULL REFERENCES public.profiles(id),
 action text NOT NULL CHECK(action IN ('hold','reaffirm')),evidence_hash text NOT NULL,notes text NOT NULL,
 evaluation_id uuid REFERENCES wholesale_ingest.lead_evaluations(id),review_id uuid REFERENCES wholesale_ingest.lot_reviews(id),
 evidence_snapshot jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(handoff_id,version)
);
ALTER TABLE wholesale_ingest.lot_reconciliations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.lot_reconciliations FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT ON wholesale_ingest.lot_reconciliations TO service_role;
CREATE FUNCTION wholesale_ingest.immutable_lot_reconciliation() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Immutable lot reconciliation'; END $$;
CREATE TRIGGER immutable_lot_reconciliation BEFORE UPDATE OR DELETE ON wholesale_ingest.lot_reconciliations
FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.immutable_lot_reconciliation();

CREATE FUNCTION wholesale_ingest.lot_handoff_state(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE handoff wholesale_ingest.lot_handoffs; decision wholesale_ingest.lot_reconciliations;
 property wholesale_ingest.properties; land public.land_leads; evaluation wholesale_ingest.lead_evaluations;
 review wholesale_ingest.lot_reviews; snapshot jsonb; evidence jsonb; reasons text[]:='{}'; ready boolean;
 effective_evaluation uuid;effective_review uuid; owner_ok boolean;destination jsonb;
BEGIN
 SELECT * INTO handoff FROM wholesale_ingest.lot_handoffs WHERE id=p_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','handoff_missing'); END IF;
 SELECT * INTO decision FROM wholesale_ingest.lot_reconciliations WHERE handoff_id=p_id ORDER BY version DESC LIMIT 1;
 SELECT * INTO property FROM wholesale_ingest.properties WHERE lead_id=handoff.lead_id;
 SELECT * INTO land FROM public.land_leads WHERE id=handoff.land_lead_id;
 SELECT * INTO evaluation FROM wholesale_ingest.lead_evaluations WHERE lead_id=handoff.lead_id AND input_snapshot IS NOT NULL ORDER BY created_at DESC,id DESC LIMIT 1;
 SELECT * INTO review FROM wholesale_ingest.lot_reviews WHERE lead_id=handoff.lead_id ORDER BY created_at DESC,id DESC LIMIT 1;
 snapshot:=public.list_scoring_input(handoff.lead_id);
 owner_ok:=EXISTS(SELECT 1 FROM public.profiles WHERE id=handoff.assigned_to AND status='approved');
 destination:=jsonb_build_object('id',land.id,'lead_id',land.lead_id,'address',land.property_address,'city',land.city,'state',land.state,'county',land.county,'parcel_id',land.apn,'zip',land.zip_code,'status',land.status);
 evidence:=jsonb_build_object('handoff_id',p_id,'version',coalesce(decision.version,0),'decision_id',decision.id,
 'property',to_jsonb(property),'destination',destination,'owner_approved',owner_ok,
 'current_input_hash',snapshot->>'input_hash','latest_evaluation',to_jsonb(evaluation),'latest_review',to_jsonb(review));
 IF property.id IS NULL OR property.is_vacant_lot IS DISTINCT FROM true THEN reasons:=array_append(reasons,'verified_lot_required'); END IF;
 IF review.id IS NULL OR review.is_vacant_lot IS DISTINCT FROM true OR review.property_snapshot IS DISTINCT FROM (to_jsonb(property)-'is_vacant_lot') THEN reasons:=array_append(reasons,'lot_review_required'); END IF;
 IF evaluation.id IS NULL OR evaluation.route IS DISTINCT FROM 'underwrite_lot' OR evaluation.prompt_version IS DISTINCT FROM 'daily-list-score-v1'
 OR snapshot->>'input_hash' IS NULL OR evaluation.input_hash IS DISTINCT FROM snapshot->>'input_hash' THEN reasons:=array_append(reasons,'current_qualifying_score_required'); END IF;
 IF land.id IS NULL OR land.lead_id IS DISTINCT FROM handoff.lead_id OR land.state IS DISTINCT FROM property.state OR land.county IS DISTINCT FROM property.county
 OR lower(trim(land.property_address)) IS DISTINCT FROM lower(trim(property.address_std)) OR lower(trim(land.city)) IS DISTINCT FROM lower(trim(property.city))
 OR nullif(trim(property.address_std),'') IS NULL OR nullif(trim(property.city),'') IS NULL OR nullif(trim(property.unit),'') IS NOT NULL
 OR (property.parcel_id IS NOT NULL AND land.apn IS DISTINCT FROM property.parcel_id)
 OR (property.zip IS NOT NULL AND land.zip_code IS DISTINCT FROM property.zip) OR land.status='dead' THEN reasons:=array_append(reasons,'destination_identity_conflict'); END IF;
 IF NOT owner_ok THEN reasons:=array_append(reasons,'assigned_owner_unavailable'); END IF;
 ready:=cardinality(reasons)=0;
 effective_evaluation:=CASE WHEN decision.action='reaffirm' THEN decision.evaluation_id ELSE handoff.evaluation_id END;
 effective_review:=CASE WHEN decision.action='reaffirm' THEN decision.review_id ELSE handoff.review_id END;
 IF decision.action='hold' THEN reasons:=array_append(reasons,'administrator_hold');
 ELSIF effective_evaluation IS DISTINCT FROM evaluation.id OR effective_review IS DISTINCT FROM review.id THEN reasons:=array_append(reasons,'new_evidence_requires_review'); END IF;
 RETURN evidence||jsonb_build_object('evidence_hash',encode(sha256(convert_to(evidence::text,'UTF8')),'hex'),
 'current',cardinality(reasons)=0,'reaffirmable',ready,'reasons',to_jsonb(reasons),
 'last_decision',CASE WHEN decision.id IS NOT NULL THEN jsonb_build_object('id',decision.id,'version',decision.version,'operator_id',decision.operator_id,'action',decision.action,'notes',decision.notes,'created_at',decision.created_at) END,
 'effective_evaluation_id',effective_evaluation,'effective_review_id',effective_review);
END $$;
CREATE FUNCTION public.reconcile_list_lot(p_id uuid,p_operator uuid,p_handoff uuid,p_version integer,p_action text,p_evidence_hash text,p_notes text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.lot_reconciliations; handoff wholesale_ingest.lot_handoffs; state jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_handoff IS NULL OR p_version IS NULL OR p_version<0 OR p_action IS NULL OR p_action NOT IN ('hold','reaffirm')
 OR coalesce(p_evidence_hash,'') !~ '^[a-f0-9]{64}$' OR coalesce(length(trim(p_notes)),0) NOT BETWEEN 1 AND 2000 THEN RETURN jsonb_build_object('blocked','invalid_reconciliation'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('lot-reconciliation:'||p_id::text,0));
 SELECT * INTO saved FROM wholesale_ingest.lot_reconciliations WHERE id=p_id;
 IF FOUND THEN
  IF saved.handoff_id<>p_handoff OR saved.operator_id<>p_operator OR saved.version<>p_version+1 OR saved.action<>p_action OR saved.evidence_hash<>p_evidence_hash OR saved.notes<>p_notes THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('event',to_jsonb(saved),'replayed',true,'outreach_authorized',false);
 END IF;
 SELECT * INTO handoff FROM wholesale_ingest.lot_handoffs WHERE id=p_handoff FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','handoff_missing'); END IF;
 PERFORM 1 FROM wholesale_ingest.properties WHERE lead_id=handoff.lead_id FOR UPDATE;
 PERFORM 1 FROM public.land_leads WHERE id=handoff.land_lead_id FOR UPDATE;
 state:=wholesale_ingest.lot_handoff_state(p_handoff);
 IF (state->>'version')::integer<>p_version THEN RETURN jsonb_build_object('blocked','version_conflict'); END IF;
 IF state->>'evidence_hash' IS DISTINCT FROM p_evidence_hash THEN RETURN jsonb_build_object('blocked','evidence_changed'); END IF;
 IF p_action='reaffirm' AND state->>'reaffirmable' IS DISTINCT FROM 'true' THEN RETURN jsonb_build_object('blocked','current_reviewed_evidence_required'); END IF;
 INSERT INTO wholesale_ingest.lot_reconciliations(id,handoff_id,version,operator_id,action,evidence_hash,notes,evaluation_id,review_id,evidence_snapshot)
 VALUES(p_id,p_handoff,p_version+1,p_operator,p_action,p_evidence_hash,p_notes,(state#>>'{latest_evaluation,id}')::uuid,(state#>>'{latest_review,id}')::uuid,state) RETURNING * INTO saved;
 -- Reconciliation cannot rewrite the original receipt, land pricing or completed analysis.
 UPDATE public.tasks SET status='pending',priority='high' WHERE id=handoff.task_id;
 RETURN jsonb_build_object('event',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.lot_handoff_state(uuid),public.reconcile_list_lot(uuid,uuid,uuid,integer,text,text,text) FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT EXECUTE ON FUNCTION wholesale_ingest.lot_handoff_state(uuid),public.reconcile_list_lot(uuid,uuid,uuid,integer,text,text,text) TO service_role;

CREATE OR REPLACE FUNCTION public.list_lot_handoffs(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE admin boolean;
BEGIN
 SELECT role='admin' INTO admin FROM public.profiles WHERE id=p_operator AND status='approved';
 IF NOT FOUND THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('count',(SELECT count(*) FROM wholesale_ingest.lot_handoffs WHERE admin OR assigned_to=p_operator),
 'handoffs',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.created_at DESC,h.id DESC),'[]') FROM (
 SELECT h.*,p.address_std,p.county,r.evidence_url,r.notes AS review_notes,e.score,e.reasons,e.flags,e.input_snapshot AS scoring_input,(state.value->>'current')::boolean AS current,state.value AS reconciliation
 FROM wholesale_ingest.lot_handoffs h JOIN wholesale_ingest.properties p ON p.lead_id=h.lead_id
 JOIN wholesale_ingest.lot_reviews r ON r.id=h.review_id JOIN wholesale_ingest.lead_evaluations e ON e.id=h.evaluation_id
 CROSS JOIN LATERAL (SELECT wholesale_ingest.lot_handoff_state(h.id) value) state
 WHERE admin OR h.assigned_to=p_operator ORDER BY h.created_at DESC,h.id DESC LIMIT 50 OFFSET p_offset) h));
END $$;

CREATE OR REPLACE FUNCTION wholesale_ingest.scan_lots_at(p_now timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_id uuid; attempt wholesale_ingest.lot_routing_attempts; late record; stale jsonb;
BEGIN
 IF p_now IS NULL THEN RAISE EXCEPTION 'Scan time required'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:lot-routing-monitor',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 UPDATE wholesale_ingest.lot_routing_attempts a SET resolved_at=p_now WHERE resolved_at IS NULL AND
 (EXISTS(SELECT 1 FROM wholesale_ingest.lot_handoffs h WHERE h.lead_id=a.lead_id)
 OR (SELECT e.route FROM wholesale_ingest.lead_evaluations e WHERE e.lead_id=a.lead_id AND e.input_snapshot IS NOT NULL ORDER BY e.created_at DESC,e.id DESC LIMIT 1) IS DISTINCT FROM 'underwrite_lot');
 FOR attempt IN SELECT * FROM wholesale_ingest.lot_routing_attempts WHERE resolved_at IS NULL AND blocked IS NOT NULL FOR UPDATE LOOP
  IF owner_id IS NOT NULL THEN
   IF attempt.task_id IS NULL THEN
    attempt.task_id:=gen_random_uuid();
    INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
    VALUES(attempt.task_id,'Lot routing needs review',attempt.blocked||'. Lead '||attempt.lead_id::text||'. Review lot identity, evidence, owner and existing destination before routing.','pending','high','follow_up',owner_id,p_now);
    UPDATE wholesale_ingest.lot_routing_attempts SET task_id=attempt.task_id WHERE lead_id=attempt.lead_id;
   ELSE
    UPDATE public.tasks SET status='pending',priority='high',assigned_to=owner_id,
    description=attempt.blocked||'. Lead '||attempt.lead_id::text||'. Review lot identity, evidence, owner and existing destination before routing.' WHERE id=attempt.task_id;
   END IF;
  END IF;
 END LOOP;
 -- The original receiving task is the reminder. Never duplicate it or mark analysis complete.
 FOR late IN SELECT h.* FROM wholesale_ingest.lot_handoffs h
 WHERE h.acknowledged_at IS NULL AND h.created_at+interval '60 minutes'<=p_now LOOP
  UPDATE public.tasks SET status='pending',priority='high' WHERE id=late.task_id;
 END LOOP;
 SELECT coalesce(jsonb_agg(jsonb_build_object('handoff_id',h.id,'lead_id',h.lead_id,'task_id',h.task_id,'reasons',s.value->'reasons') ORDER BY h.created_at,h.id),'[]') INTO stale
 FROM wholesale_ingest.lot_handoffs h CROSS JOIN LATERAL (SELECT wholesale_ingest.lot_handoff_state(h.id) value) s
 WHERE s.value->>'current' IS DISTINCT FROM 'true';
 UPDATE public.tasks SET status='pending',priority='high' WHERE id IN (SELECT (entry->>'task_id')::uuid FROM jsonb_array_elements(stale) entry);
 RETURN jsonb_build_object('stale_handoffs',stale,'owner_configured',owner_id IS NOT NULL,
 'open_incidents',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY last_attempt_at,lead_id),'[]') FROM wholesale_ingest.lot_routing_attempts a WHERE resolved_at IS NULL AND blocked IS NOT NULL),
 'overdue_receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('handoff_id',h.id,'lead_id',h.lead_id,'task_id',h.task_id,'assigned_to',h.assigned_to,'created_at',h.created_at) ORDER BY h.created_at,h.id),'[]') FROM wholesale_ingest.lot_handoffs h WHERE h.acknowledged_at IS NULL AND h.created_at+interval '60 minutes'<=p_now));
END $$;
