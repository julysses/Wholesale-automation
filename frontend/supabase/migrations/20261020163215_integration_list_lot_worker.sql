-- Selective integration from 8bec6d825071993d59bc623b346046c3f249fba2
-- Source: 20261013013234_list_lot_worker.sql; NEW forward migration, never apply the historical source as well.
-- Unapplied: production deployment and migration approval remain separate.
GRANT SELECT ON public.app_settings TO service_role;
GRANT UPDATE ON public.tasks TO service_role;
-- Automated handoffs have their own origin, never a fabricated human actor.
ALTER TABLE wholesale_ingest.lot_handoffs ALTER COLUMN operator_id DROP NOT NULL;
ALTER TABLE wholesale_ingest.lot_handoffs ADD COLUMN initiation text NOT NULL DEFAULT 'operator'
 CHECK(initiation IN ('operator','worker'));
ALTER TABLE wholesale_ingest.lot_handoffs ADD CONSTRAINT lot_initiator_valid
 CHECK((initiation='operator' AND operator_id IS NOT NULL) OR (initiation='worker' AND operator_id IS NULL));
CREATE TABLE wholesale_ingest.lot_routing_attempts (
 lead_id uuid PRIMARY KEY REFERENCES public.leads(id),evaluation_id uuid NOT NULL REFERENCES wholesale_ingest.lead_evaluations(id),
 last_attempt_at timestamptz NOT NULL,attempts integer NOT NULL DEFAULT 1,blocked text,
 task_id uuid REFERENCES public.tasks(id),resolved_at timestamptz
);
ALTER TABLE wholesale_ingest.lot_routing_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.lot_routing_attempts FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.lot_routing_attempts TO service_role;
CREATE FUNCTION wholesale_ingest.handoff_lot(p_id uuid,p_operator uuid,p_evaluation uuid,p_assignee uuid,p_initiation text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE evaluation wholesale_ingest.lead_evaluations; review wholesale_ingest.lot_reviews; property wholesale_ingest.properties;
 saved wholesale_ingest.lot_handoffs; land public.land_leads; task uuid; snapshot jsonb; matches integer;
BEGIN
 IF p_initiation IS NULL OR p_initiation NOT IN ('operator','worker') OR (p_initiation='worker' AND p_operator IS NOT NULL) THEN RAISE EXCEPTION 'Invalid initiation'; END IF;
 IF p_initiation='operator' AND NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_evaluation IS NULL OR p_assignee IS NULL THEN RETURN jsonb_build_object('blocked','invalid_handoff'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('lot-handoff:'||p_id::text,0));
 SELECT * INTO saved FROM wholesale_ingest.lot_handoffs WHERE id=p_id;
 IF FOUND THEN
  IF saved.operator_id IS DISTINCT FROM p_operator OR saved.initiation<>p_initiation OR saved.evaluation_id<>p_evaluation OR saved.assigned_to<>p_assignee THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
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
 INSERT INTO wholesale_ingest.lot_handoffs(id,lead_id,evaluation_id,review_id,operator_id,assigned_to,land_lead_id,task_id,input_hash,initiation)
 VALUES(p_id,evaluation.lead_id,evaluation.id,review.id,p_operator,p_assignee,land.id,task,evaluation.input_hash,p_initiation) RETURNING * INTO saved;
 RETURN jsonb_build_object('handoff',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION public.handoff_list_lot(p_id uuid,p_operator uuid,p_evaluation uuid,p_assignee uuid) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT wholesale_ingest.handoff_lot(p_id,p_operator,p_evaluation,p_assignee,'operator');
$$;
CREATE FUNCTION public.route_list_lots(p_limit integer DEFAULT 5) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE candidate record; owner_id uuid; result jsonb; reason text; outcomes jsonb:='[]';
BEGIN
 IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 10 THEN RAISE EXCEPTION 'Invalid routing limit'; END IF;
 -- A single short database transaction: no model, tracing or messaging requests.
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:lot-routing-worker',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 FOR candidate IN
  SELECT e.id,e.lead_id FROM
   (SELECT DISTINCT ON (lead_id) * FROM wholesale_ingest.lead_evaluations WHERE input_snapshot IS NOT NULL
    ORDER BY lead_id,created_at DESC,id DESC) e
  LEFT JOIN wholesale_ingest.lot_routing_attempts a ON a.lead_id=e.lead_id
  WHERE e.route='underwrite_lot' AND e.prompt_version='daily-list-score-v1'
   AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.lot_handoffs h WHERE h.lead_id=e.lead_id)
  ORDER BY a.last_attempt_at NULLS FIRST,e.created_at,e.id LIMIT p_limit
 LOOP
  result:=NULL;reason:=NULL;
  IF owner_id IS NULL THEN reason:='owner_not_configured';
  ELSE
   BEGIN
    result:=wholesale_ingest.handoff_lot(gen_random_uuid(),NULL,candidate.id,owner_id,'worker');
    reason:=result->>'blocked';
    -- A concurrent manual handoff fulfills routing; preserve its human receipt.
    IF reason='existing_handoff' THEN reason:=NULL; END IF;
   EXCEPTION WHEN OTHERS THEN
    -- Roll back this candidate's land/task writes. Do not leak raw database data.
    reason:='routing_error_'||SQLSTATE;
   END;
  END IF;
  INSERT INTO wholesale_ingest.lot_routing_attempts(lead_id,evaluation_id,last_attempt_at,blocked,resolved_at)
  VALUES(candidate.lead_id,candidate.id,clock_timestamp(),reason,CASE WHEN reason IS NULL THEN now() END)
  ON CONFLICT(lead_id) DO UPDATE SET evaluation_id=excluded.evaluation_id,last_attempt_at=excluded.last_attempt_at,
   attempts=wholesale_ingest.lot_routing_attempts.attempts+1,blocked=excluded.blocked,resolved_at=excluded.resolved_at;
  outcomes:=outcomes||jsonb_build_array(jsonb_build_object('lead_id',candidate.lead_id,'evaluation_id',candidate.id,
   'blocked',reason,'handoff_id',result->'handoff'->>'id'));
 END LOOP;
 RETURN jsonb_build_object('outcomes',outcomes,'outreach_authorized',false);
END $$;
CREATE FUNCTION wholesale_ingest.scan_lots_at(p_now timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_id uuid; attempt wholesale_ingest.lot_routing_attempts; late record;
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
 RETURN jsonb_build_object('owner_configured',owner_id IS NOT NULL,
 'open_incidents',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY last_attempt_at,lead_id),'[]') FROM wholesale_ingest.lot_routing_attempts a WHERE resolved_at IS NULL AND blocked IS NOT NULL),
 'overdue_receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('handoff_id',h.id,'lead_id',h.lead_id,'task_id',h.task_id,'assigned_to',h.assigned_to,'created_at',h.created_at) ORDER BY h.created_at,h.id),'[]') FROM wholesale_ingest.lot_handoffs h WHERE h.acknowledged_at IS NULL AND h.created_at+interval '60 minutes'<=p_now));
END $$;
CREATE FUNCTION public.monitor_list_lots() RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT wholesale_ingest.scan_lots_at(now()); $$;
REVOKE ALL ON FUNCTION wholesale_ingest.handoff_lot(uuid,uuid,uuid,uuid,text),public.route_list_lots(integer),wholesale_ingest.scan_lots_at(timestamptz),public.monitor_list_lots() FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT EXECUTE ON FUNCTION wholesale_ingest.handoff_lot(uuid,uuid,uuid,uuid,text),public.route_list_lots(integer),wholesale_ingest.scan_lots_at(timestamptz),public.monitor_list_lots() TO service_role;

CREATE OR REPLACE FUNCTION public.scan_list_pipeline() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_summary jsonb; ranked jsonb;
BEGIN
 v_summary:=wholesale_ingest.scan_at(now());
 IF v_summary->>'busy'='true' THEN RETURN v_summary; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.score DESC,t.created_at DESC,t.lead_id),'[]') INTO ranked FROM (
  SELECT latest.lead_id,latest.score,latest.reasons,latest.flags,latest.route,latest.created_at
  FROM (SELECT DISTINCT ON (lead_id) * FROM wholesale_ingest.lead_evaluations ORDER BY lead_id,created_at DESC,id DESC) latest
  WHERE latest.input_snapshot IS NOT NULL AND latest.prompt_version='daily-list-score-v1'
  AND latest.input_hash=public.list_scoring_input(latest.lead_id)->>'input_hash'
  ORDER BY latest.score DESC,latest.created_at DESC,latest.lead_id LIMIT 10
 ) t;
 v_summary:=jsonb_set(v_summary,'{top_ten}',ranked);
 v_summary:=v_summary||jsonb_build_object('scoring_monitor',wholesale_ingest.scan_scoring_at(now()));
 v_summary:=v_summary||jsonb_build_object('lot_routing_monitor',wholesale_ingest.scan_lots_at(now()));
 UPDATE wholesale_ingest.daily_digests SET summary=v_summary WHERE day=(v_summary->>'day')::date;
 RETURN v_summary;
END $$;
