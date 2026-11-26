BEGIN;
ALTER TABLE wholesale_ingest.distress_signals ADD COLUMN status_review_id uuid;
ALTER TABLE wholesale_ingest.propstream_events ALTER COLUMN request_id DROP NOT NULL;
ALTER TABLE wholesale_ingest.propstream_events ADD COLUMN status_review jsonb;
ALTER TABLE wholesale_ingest.propstream_events DROP CONSTRAINT propstream_events_action_check;
ALTER TABLE wholesale_ingest.propstream_events ADD CONSTRAINT propstream_events_action_check CHECK(action IN ('prepare','start','reconcile','review_status'));
CREATE OR REPLACE FUNCTION public.propstream_handoff_snapshot(p_operator uuid,p_offset int DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE items jsonb:='[]'; p record; input jsonb; trace jsonb; stage text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_offset IS NULL OR p_offset<0 THEN RAISE EXCEPTION 'Invalid offset'; END IF;
 FOR p IN SELECT pr.lead_id,pr.county,pr.address_std,pr.city,pr.zip,l.status,coalesce((to_jsonb(l)->>'dnc')::boolean,false) AS dnc,
 sg.id AS signal_id,sg.auction_date,sg.active,sg.source_url,
 md5(jsonb_build_object('id',sg.id,'active',sg.active,'auction_date',sg.auction_date,'last_run_id',sg.last_run_id,'last_seen_at',sg.last_seen_at,'status_review_id',sg.status_review_id)::text) AS signal_hash
 FROM wholesale_ingest.properties pr JOIN public.leads l ON l.id=pr.lead_id
 JOIN LATERAL(SELECT * FROM wholesale_ingest.distress_signals s WHERE s.property_id=pr.id AND s.list_type='pre_foreclosure' ORDER BY s.active DESC,s.auction_date DESC NULLS LAST,s.id LIMIT 1) sg ON true
 ORDER BY sg.auction_date NULLS LAST,pr.lead_id LIMIT 50 OFFSET p_offset LOOP
  input:=public.list_trace_input(p.lead_id);
  SELECT to_jsonb(r) INTO trace FROM wholesale_ingest.skip_trace_requests r WHERE r.lead_id=p.lead_id ORDER BY created_at DESC,id DESC LIMIT 1;
  stage:=CASE WHEN trace->>'state' IN ('submitted','unknown') THEN 'reconciliation_required'
   WHEN p.dnc OR p.status IN ('dnc','dead','sold','under_contract') THEN 'suppressed'
   WHEN trace->>'state'='reserved' THEN 'reserved'
   WHEN trace->>'state'='completed' THEN 'result_saved'
   WHEN NOT p.active OR p.auction_date IS NULL OR p.auction_date<(clock_timestamp() AT TIME ZONE 'America/Chicago')::date THEN 'current_status_review'
   WHEN input ? 'blocked' THEN input->>'blocked' ELSE 'quote_and_evidence_required' END;
  items:=items||jsonb_build_array(to_jsonb(p)||jsonb_build_object('stage',stage,'input',input->'input','input_hash',input->'input_hash',
   'request',trace,'contacts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'name',name,'phone',phone,'email',email,'dnc_status',dnc_status,'expires_at',expires_at)),'[]') FROM wholesale_ingest.contacts WHERE trace_request_id=(trace->>'id')::uuid),
   'handoff',(SELECT to_jsonb(h) FROM wholesale_ingest.propstream_handoffs h WHERE request_id=(trace->>'id')::uuid)));
 END LOOP;
 RETURN jsonb_build_object('total_budget',public.list_trace_total_budget(),'items',items,'total',
 (SELECT count(*) FROM wholesale_ingest.properties pr WHERE EXISTS(SELECT 1 FROM wholesale_ingest.distress_signals s WHERE s.property_id=pr.id AND s.list_type='pre_foreclosure')));
END; $$;

CREATE OR REPLACE FUNCTION public.propstream_handoff_action(p_event uuid,p_operator uuid,p_request uuid,p_lead uuid,p_action text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE old wholesale_ingest.propstream_events; saved wholesale_ingest.skip_trace_requests; h wholesale_ingest.propstream_handoffs;
 signal wholesale_ingest.distress_signals; input jsonb; result jsonb; lead jsonb; signal_hash text; task uuid; host text; owner_id uuid;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_event IS NULL OR p_request IS NULL OR p_lead IS NULL OR p_action IS NULL OR p_action NOT IN ('prepare','start','reconcile','review_status') OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Invalid handoff'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('propstream-event:'||p_event::text,0));
 IF EXISTS(SELECT 1 FROM wholesale_ingest.propstream_abandoned_events WHERE id=p_event) THEN RAISE EXCEPTION 'Saved action abandoned during recovery'; END IF;
 SELECT * INTO old FROM wholesale_ingest.propstream_events WHERE id=p_event;
 IF FOUND THEN
  IF old.operator_id<>p_operator OR old.result->>'request_id' IS DISTINCT FROM p_request::text OR old.action<>p_action OR old.payload_hash IS DISTINCT FROM encode(sha256(convert_to((p_payload||jsonb_build_object('lead_id',p_lead))::text,'UTF8')),'hex') THEN RAISE EXCEPTION 'Handoff reference conflict'; END IF;
  RETURN old.result||jsonb_build_object('replayed',true,'dispatch',false);
 END IF;
 -- Match the core lead reservation lock before inspecting/changing handoff state.
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-lead:'||p_lead::text,0));
 SELECT to_jsonb(l) INTO lead FROM public.leads l WHERE id=p_lead FOR UPDATE;
 IF lead IS NULL THEN RAISE EXCEPTION 'Lead missing'; END IF;
 IF p_action='review_status' THEN
  IF (p_payload-ARRAY['signal_id','signal_hash','active','auction_date','status_evidence_url','notes','confirmed_current_status'])<>'{}'::jsonb
   OR p_payload->'confirmed_current_status' IS DISTINCT FROM 'true'::jsonb
   OR jsonb_typeof(p_payload->'active') IS DISTINCT FROM 'boolean'
   OR coalesce(length(trim(p_payload->>'notes')),0) NOT BETWEEN 20 AND 2000
   THEN RAISE EXCEPTION 'Current status review and evidence required'; END IF;
  SELECT s.* INTO signal FROM wholesale_ingest.distress_signals s JOIN wholesale_ingest.properties p ON p.id=s.property_id
   WHERE s.id=(p_payload->>'signal_id')::uuid AND p.lead_id=p_lead AND s.list_type='pre_foreclosure' FOR UPDATE OF s;
  IF signal.id IS NULL THEN RAISE EXCEPTION 'Matching foreclosure signal required'; END IF;
  signal_hash:=md5(jsonb_build_object('id',signal.id,'active',signal.active,'auction_date',signal.auction_date,'last_run_id',signal.last_run_id,'last_seen_at',signal.last_seen_at,'status_review_id',signal.status_review_id)::text);
  IF p_payload->>'signal_hash' IS DISTINCT FROM signal_hash THEN RAISE EXCEPTION 'Foreclosure evidence changed'; END IF;
  host:=p_payload->>'status_evidence_url';
  IF coalesce(length(host),0)>2000 OR substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)') IS NULL OR
   substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)')<>ALL(CASE WHEN (SELECT county FROM wholesale_ingest.sources WHERE id=signal.source_id)='Dallas' THEN ARRAY['www.dallascounty.org','dallas.tx.publicsearch.us'] ELSE ARRAY['www.collincountytx.gov','collincountytx.gov','apps.collincountytx.gov','apps2.collincountytx.gov'] END) THEN RAISE EXCEPTION 'Official current-sale evidence required'; END IF;
  IF coalesce(p_payload->>'auction_date','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'Exact sale date required'; END IF;
  IF (p_payload->>'active')::boolean AND ((p_payload->>'auction_date')::date<(clock_timestamp() AT TIME ZONE 'America/Chicago')::date
   OR coalesce((lead->>'dnc')::boolean,false) OR lead->>'status' IN ('dnc','dead','sold','under_contract')) THEN RAISE EXCEPTION 'Active sale cannot be past or suppressed'; END IF;
  -- Changing this version invalidates any previously reserved quote at claim time.
  -- Submitted provider orders remain reconcilable even when a sale is canceled.
  UPDATE wholesale_ingest.distress_signals SET active=(p_payload->>'active')::boolean,
   auction_date=(p_payload->>'auction_date')::date,status_review_id=p_event WHERE id=signal.id;
  result:=jsonb_build_object('status_reviewed',true,'signal_id',signal.id,'active',(p_payload->>'active')::boolean,'dispatch',false);
 ELSIF p_action='prepare' THEN
  IF (p_payload-ARRAY['input_hash','signal_id','signal_hash','quote_cents','prepaid_balance_cents','quote_reference','owner_evidence_url','status_evidence_url','notes','all_pages_reviewed'])<>'{}'::jsonb THEN RAISE EXCEPTION 'Unexpected prepare fields'; END IF;
  IF coalesce((lead->>'dnc')::boolean,false) OR lead->>'status' IN ('dnc','dead','sold','under_contract') THEN RAISE EXCEPTION 'Lead suppressed'; END IF;
  SELECT s.* INTO signal FROM wholesale_ingest.distress_signals s JOIN wholesale_ingest.properties p ON p.id=s.property_id
   WHERE s.id=(p_payload->>'signal_id')::uuid AND p.lead_id=p_lead AND s.list_type='pre_foreclosure' FOR UPDATE OF s;
  IF signal.id IS NULL OR NOT signal.active OR signal.auction_date IS NULL OR signal.auction_date<(clock_timestamp() AT TIME ZONE 'America/Chicago')::date THEN RAISE EXCEPTION 'Current active foreclosure evidence required'; END IF;
  signal_hash:=md5(jsonb_build_object('id',signal.id,'active',signal.active,'auction_date',signal.auction_date,'last_run_id',signal.last_run_id,'last_seen_at',signal.last_seen_at,'status_review_id',signal.status_review_id)::text);
  IF p_payload->>'signal_hash' IS DISTINCT FROM signal_hash THEN RAISE EXCEPTION 'Foreclosure evidence changed'; END IF;
  IF p_payload->'all_pages_reviewed' IS DISTINCT FROM 'true'::jsonb OR coalesce(length(trim(p_payload->>'notes')),0) NOT BETWEEN 20 AND 2000 OR coalesce(length(trim(p_payload->>'quote_reference')),0) NOT BETWEEN 3 AND 255 THEN RAISE EXCEPTION 'Notice review and exact quote reference required'; END IF;
  FOREACH host IN ARRAY ARRAY[p_payload->>'owner_evidence_url',p_payload->>'status_evidence_url'] LOOP
   IF coalesce(length(host),0)>2000 OR substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)') IS NULL OR
    substring(lower(host) from '^https://([^/:?#]+)(?:[/:?#]|$)')<>ALL(CASE WHEN (SELECT county FROM wholesale_ingest.sources WHERE id=signal.source_id)='Dallas' THEN ARRAY['www.dallascad.org','dallascad.org','www.dallascounty.org','dallas.tx.publicsearch.us'] ELSE ARRAY['www.collincad.org','collincad.org','www.collincountytx.gov','collincountytx.gov','gis.collincountytx.gov','apps.collincountytx.gov','apps2.collincountytx.gov','esearch.collincad.org'] END) THEN RAISE EXCEPTION 'Official owner and status evidence required'; END IF;
  END LOOP;
  IF coalesce(p_payload->>'quote_cents','') !~ '^[1-9][0-9]{0,3}$' OR (p_payload->>'quote_cents')::int>5000 OR coalesce(p_payload->>'prepaid_balance_cents','') !~ '^[0-9]{1,9}$' OR (p_payload->>'quote_cents')::int>(p_payload->>'prepaid_balance_cents')::int THEN RAISE EXCEPTION 'Quote exceeds confirmed prepaid balance or total cap'; END IF;
  input:=public.list_trace_input(p_lead);
  IF input ? 'blocked' OR input->>'input_hash' IS DISTINCT FROM p_payload->>'input_hash' THEN RAISE EXCEPTION 'Trace identity unavailable or changed: %',input->>'blocked'; END IF;
  INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,5000) ON CONFLICT DO NOTHING;
  result:=public.prepare_list_trace(p_request,p_lead,'propstream', (p_payload->>'quote_cents')::int);
  IF result ? 'blocked' THEN RAISE EXCEPTION 'Trace reservation blocked: %',result->>'blocked'; END IF;
  IF result->>'replayed'='true' THEN RAISE EXCEPTION 'Request already exists; recover its original event'; END IF;
  INSERT INTO wholesale_ingest.propstream_handoffs(request_id,operator_id,review,signal_id,signal_hash) VALUES(p_request,p_operator,p_payload,signal.id,signal_hash);
 ELSE
  SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_request FOR UPDATE;
  SELECT * INTO h FROM wholesale_ingest.propstream_handoffs WHERE request_id=p_request FOR UPDATE;
  IF saved.id IS NULL OR h.request_id IS NULL OR saved.lead_id<>p_lead OR saved.provider<>'propstream' THEN RAISE EXCEPTION 'Matching PropStream handoff required'; END IF;
  IF p_action='start' THEN
   IF p_payload<>jsonb_build_object('input_hash',saved.input_hash) THEN RAISE EXCEPTION 'Input mismatch'; END IF;
   IF coalesce((lead->>'dnc')::boolean,false) OR lead->>'status' IN ('dnc','dead','sold','under_contract') THEN RAISE EXCEPTION 'Lead suppressed'; END IF;
   SELECT * INTO signal FROM wholesale_ingest.distress_signals WHERE id=h.signal_id FOR UPDATE;
   signal_hash:=md5(jsonb_build_object('id',signal.id,'active',signal.active,'auction_date',signal.auction_date,'last_run_id',signal.last_run_id,'last_seen_at',signal.last_seen_at,'status_review_id',signal.status_review_id)::text);
   IF signal_hash<>h.signal_hash OR NOT signal.active OR signal.auction_date<(clock_timestamp() AT TIME ZONE 'America/Chicago')::date OR h.created_at<clock_timestamp()-interval '24 hours' THEN RAISE EXCEPTION 'Recheck current foreclosure evidence'; END IF;
   result:=public.claim_list_trace(p_request,saved.input_hash);
  ELSE
   IF (p_payload-ARRAY['input_hash','actual_cents','provider_receipt','contacts','confirmed_match'])<>'{}'::jsonb OR p_payload->'confirmed_match' IS DISTINCT FROM 'true'::jsonb OR p_payload->>'input_hash' IS DISTINCT FROM saved.input_hash OR coalesce(p_payload->>'actual_cents','') !~ '^[0-9]{1,4}$' THEN RAISE EXCEPTION 'Matching provider result and cost required'; END IF;
   result:=public.complete_list_trace(p_request,'propstream',saved.input_hash,(p_payload->>'actual_cents')::int,p_payload->>'provider_receipt',p_payload->'contacts');
   IF NOT (result ? 'blocked') AND h.follow_up_task_id IS NULL THEN
    SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value AND p.status='approved' WHERE a.key='lead_owner_user_id';
    owner_id:=coalesce(owner_id,p_operator);task:=gen_random_uuid();
    INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date,lead_id)
     VALUES(task,CASE WHEN (result->>'contacts_saved')::int>0 THEN 'Foreclosure contact found — review outreach eligibility' ELSE 'Foreclosure trace returned no contacts — review next action' END,
      'Lead '||p_lead||'; PropStream request '||p_request||'. Review matched contacts and channel eligibility in Daily Lists. No outreach authorized or sent.', 'pending','high','follow_up',owner_id,clock_timestamp(),p_lead);
    UPDATE wholesale_ingest.propstream_handoffs SET follow_up_task_id=task WHERE request_id=p_request;
    result:=result||jsonb_build_object('follow_up_task_id',task);
   END IF;
  END IF;
  IF result ? 'blocked' THEN RAISE EXCEPTION 'Trace handoff blocked: %',result->>'blocked'; END IF;
 END IF;
 result:=result||jsonb_build_object('event_id',p_event,'request_id',p_request,'lead_id',p_lead,'operator_id',p_operator,'action',p_action,'outreach_authorized',false);
 INSERT INTO wholesale_ingest.propstream_events(id,operator_id,request_id,action,payload_hash,result,status_review) VALUES(p_event,p_operator,CASE WHEN p_action='review_status' THEN NULL ELSE p_request END,p_action,encode(sha256(convert_to((p_payload||jsonb_build_object('lead_id',p_lead))::text,'UTF8')),'hex'),result,CASE WHEN p_action='review_status' THEN p_payload END);
 RETURN result;
END; $$;
REVOKE ALL ON FUNCTION public.propstream_handoff_snapshot(uuid,int),public.propstream_handoff_action(uuid,uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.propstream_handoff_snapshot(uuid,int),public.propstream_handoff_action(uuid,uuid,uuid,uuid,text,jsonb) TO service_role;

COMMIT;
