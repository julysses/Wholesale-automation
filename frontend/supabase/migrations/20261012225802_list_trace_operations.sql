CREATE TABLE wholesale_ingest.trace_operator_events (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL REFERENCES public.profiles(id),
 request_id uuid NOT NULL REFERENCES wholesale_ingest.skip_trace_requests(id),
 action text NOT NULL CHECK(action='cancel_reserved'), result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE wholesale_ingest.trace_operator_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.trace_operator_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.trace_operator_events TO service_role;
CREATE INDEX trace_operator_events_request ON wholesale_ingest.trace_operator_events(request_id,created_at);
CREATE FUNCTION public.list_trace_operations(p_operator uuid,p_offset integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE today date:=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 RETURN jsonb_build_object('day',today,'budget',(SELECT to_jsonb(b) FROM wholesale_ingest.daily_budgets b WHERE spend_day=today),
  'total_held_cents',(SELECT coalesce(sum(reserved_cents),0) FROM wholesale_ingest.daily_budgets),
  'open_count',(SELECT count(*) FROM wholesale_ingest.skip_trace_requests WHERE state IN ('reserved','submitted','unknown')),
  'requests',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.created_at,r.id),'[]') FROM (
   SELECT id,lead_id,provider,spend_day,reserved_cents,state,created_at FROM wholesale_ingest.skip_trace_requests
   WHERE state IN ('reserved','submitted','unknown') ORDER BY created_at,id LIMIT 50 OFFSET p_offset) r),
  'recent_actions',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.created_at DESC,e.id DESC),'[]') FROM (
   SELECT id,operator_id,request_id,action,created_at FROM wholesale_ingest.trace_operator_events ORDER BY created_at DESC,id DESC LIMIT 20) e));
END $$;
CREATE FUNCTION public.cancel_list_trace_as_operator(p_id uuid,p_request uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE event wholesale_ingest.trace_operator_events; result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR p_request IS NULL THEN RETURN jsonb_build_object('blocked','invalid_reference'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-operator:'||p_id::text,0));
 SELECT * INTO event FROM wholesale_ingest.trace_operator_events WHERE id=p_id;
 IF FOUND THEN
  IF event.operator_id<>p_operator OR event.request_id<>p_request THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('event',to_jsonb(event),'replayed',true);
 END IF;
 result:=public.cancel_reserved_list_trace(p_request);
 IF result ? 'blocked' THEN RETURN result; END IF;
 INSERT INTO wholesale_ingest.trace_operator_events(id,operator_id,request_id,action,result)
 VALUES(p_id,p_operator,p_request,'cancel_reserved',result) RETURNING * INTO event;
 RETURN jsonb_build_object('event',to_jsonb(event),'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.list_trace_operations(uuid,integer),public.cancel_list_trace_as_operator(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_trace_operations(uuid,integer),public.cancel_list_trace_as_operator(uuid,uuid,uuid) TO service_role;
