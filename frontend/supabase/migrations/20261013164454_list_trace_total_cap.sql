-- Owner authorization: $50 TOTAL, never a daily refill. No budgets or paid workers enabled.
-- Includes all historical providers/days; uncertain outcomes keep their full reservation.
CREATE FUNCTION public.list_trace_total_budget() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 WITH totals AS (
  SELECT coalesce(sum(CASE WHEN state IN ('reserved','submitted','unknown') OR actual_cents IS NULL
                          THEN reserved_cents ELSE 0 END),0)::bigint AS held,
         coalesce(sum(CASE WHEN state NOT IN ('reserved','submitted','unknown') AND actual_cents IS NOT NULL
                          THEN actual_cents ELSE 0 END),0)::bigint AS spent
  FROM wholesale_ingest.skip_trace_requests
 )
 SELECT jsonb_build_object('cap_cents',5000,'reserved_cents',held,'actual_cents',spent,
                          'committed_cents',held+spent,'remaining_cents',greatest(0,5000-held-spent)) FROM totals;
$$;
REVOKE ALL ON FUNCTION public.list_trace_total_budget() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_trace_total_budget() TO service_role;

CREATE OR REPLACE FUNCTION public.reserve_list_trace(p_id uuid,p_lead uuid,p_provider text,p_input_hash text,p_max_cents integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests; budget wholesale_ingest.daily_budgets;
 day date:=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date; lead_json jsonb; total_budget jsonb;
BEGIN
 IF p_id IS NULL OR p_lead IS NULL OR coalesce(p_provider,'') !~ '^[a-z0-9_-]{1,64}$'
 OR coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$' OR p_max_cents IS NULL OR p_max_cents<=0
 THEN RETURN jsonb_build_object('blocked','invalid_request'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-lead:'||p_lead::text,0));
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id<>p_lead OR saved.provider<>p_provider OR saved.input_hash IS DISTINCT FROM p_input_hash
   OR saved.reserved_cents<>p_max_cents THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',true,'dispatch',false);
 END IF;
 SELECT to_jsonb(l) INTO lead_json FROM public.leads l WHERE id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','lead_missing'); END IF;
 IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.properties WHERE lead_id=p_lead AND state='TX' AND county IN ('Dallas','Collin'))
 THEN RETURN jsonb_build_object('blocked','unverified_pipeline_property'); END IF;
 IF coalesce(nullif(trim(lead_json->>'owner_phone_1'),''),nullif(trim(lead_json->>'owner_phone_2'),''),nullif(trim(lead_json->>'owner_email'),'')) IS NOT NULL
 OR EXISTS(SELECT 1 FROM wholesale_ingest.contacts WHERE lead_id=p_lead AND expires_at>clock_timestamp())
 OR EXISTS(SELECT 1 FROM wholesale_ingest.skip_trace_requests WHERE lead_id=p_lead AND state='completed')
 THEN RETURN jsonb_build_object('blocked','already_enriched'); END IF;
 IF EXISTS(SELECT 1 FROM wholesale_ingest.skip_trace_requests WHERE lead_id=p_lead AND state IN ('reserved','submitted','unknown'))
 THEN RETURN jsonb_build_object('blocked','unresolved_request'); END IF;
 -- Serialize every new reservation across all days and providers. Midnight never resets authorization.
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-total-cap-v1',0));
 total_budget:=public.list_trace_total_budget();
 IF p_max_cents::bigint>(total_budget->>'remaining_cents')::bigint
 THEN RETURN jsonb_build_object('blocked','total_cap','total_budget',total_budget); END IF;
 SELECT * INTO budget FROM wholesale_ingest.daily_budgets WHERE spend_day=day FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','budget_not_configured'); END IF;
 IF p_max_cents::bigint+budget.reserved_cents+budget.actual_cents>budget.cap_cents
 THEN RETURN jsonb_build_object('blocked','daily_cap'); END IF;
 INSERT INTO wholesale_ingest.skip_trace_requests(id,lead_id,provider,request_key,spend_day,reserved_cents,state,input_hash)
 VALUES(p_id,p_lead,p_provider,p_id::text,day,p_max_cents,'reserved',p_input_hash) RETURNING * INTO saved;
 UPDATE wholesale_ingest.daily_budgets SET reserved_cents=reserved_cents+p_max_cents WHERE spend_day=day;
 RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',false,'dispatch',false);
END $$;


CREATE OR REPLACE FUNCTION public.claim_list_trace(p_id uuid,p_input_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests; snapshot jsonb; total_budget jsonb;
BEGIN
 IF coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$' THEN RETURN jsonb_build_object('blocked','invalid_input_identity'); END IF;
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF saved.input_snapshot IS NULL THEN RETURN jsonb_build_object('blocked','input_snapshot_missing'); END IF;
 IF saved.input_hash IS DISTINCT FROM p_input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 IF saved.state<>'reserved' THEN RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',false); END IF;
 IF saved.spend_day<>(clock_timestamp() AT TIME ZONE 'America/Chicago')::date THEN RETURN jsonb_build_object('blocked','reservation_expired'); END IF;
 -- Existing pre-migration reservations cannot bypass the cumulative authorization.
 total_budget:=public.list_trace_total_budget();
 IF (total_budget->>'committed_cents')::bigint>(total_budget->>'cap_cents')::bigint
 THEN RETURN jsonb_build_object('blocked','total_cap','total_budget',total_budget); END IF;
 snapshot:=public.list_trace_input(saved.lead_id);
 IF snapshot ? 'blocked' THEN RETURN snapshot; END IF;
 IF snapshot->>'input_hash'<>saved.input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET state='submitted' WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('request',to_jsonb(saved),'input',snapshot->'input','dispatch',true);
END $$;

CREATE OR REPLACE FUNCTION public.list_trace_operations(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE today date:=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('total_budget',public.list_trace_total_budget(),'day',today,'budget',(SELECT to_jsonb(b) FROM wholesale_ingest.daily_budgets b WHERE spend_day=today),
  'total_held_cents',(SELECT coalesce(sum(reserved_cents),0) FROM wholesale_ingest.daily_budgets),
  'open_count',(SELECT count(*) FROM wholesale_ingest.skip_trace_requests WHERE state IN ('reserved','submitted','unknown')),
  'requests',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.created_at,r.id),'[]') FROM (
   SELECT id,lead_id,provider,spend_day,reserved_cents,state,created_at FROM wholesale_ingest.skip_trace_requests
   WHERE state IN ('reserved','submitted','unknown') ORDER BY created_at,id LIMIT 50 OFFSET p_offset) r),
  'recent_actions',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.created_at DESC,e.id DESC),'[]') FROM (
   SELECT id,operator_id,request_id,action,created_at FROM wholesale_ingest.trace_operator_events ORDER BY created_at DESC,id DESC LIMIT 20) e));
END $$;

REVOKE ALL ON FUNCTION public.reserve_list_trace(uuid,uuid,text,text,integer),public.claim_list_trace(uuid,text),public.list_trace_operations(uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_list_trace(uuid,uuid,text,text,integer),public.claim_list_trace(uuid,text),public.list_trace_operations(uuid,integer) TO service_role;
