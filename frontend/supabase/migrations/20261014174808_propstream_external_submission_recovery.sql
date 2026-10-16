BEGIN;
-- Adopt evidence of an already-visible provider job. This cannot dispatch work,
-- create a reservation, settle a charge, change input identity or release money.
CREATE TABLE wholesale_ingest.propstream_external_submissions (
 id uuid PRIMARY KEY, operator_id uuid NOT NULL REFERENCES public.profiles,
 payload_hash text NOT NULL, payload jsonb NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE wholesale_ingest.propstream_external_submissions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.propstream_external_submissions FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.propstream_external_submissions TO service_role;
CREATE FUNCTION public.recover_propstream_external_submission(p_id uuid,p_operator uuid,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE old wholesale_ingest.propstream_external_submissions; item jsonb; saved wholesale_ingest.skip_trace_requests;
 fingerprint text; results jsonb:='[]'; result jsonb; job text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_id IS NULL OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
 OR (p_payload-ARRAY['provider_job_id','evidence_sha256','notes','items'])<>'{}'::jsonb
 OR coalesce(p_payload->>'provider_job_id','') !~ '^A[0-9]{1,20}$'
 OR coalesce(p_payload->>'evidence_sha256','') !~ '^[a-f0-9]{64}$'
 OR coalesce(length(trim(p_payload->>'notes')),0) NOT BETWEEN 20 AND 2000
 OR jsonb_typeof(p_payload->'items') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Exact external job evidence required'; END IF;
 IF jsonb_array_length(p_payload->'items') NOT BETWEEN 1 AND 500
 OR (SELECT count(DISTINCT v->>'request_id') FROM jsonb_array_elements(p_payload->'items') v)<>jsonb_array_length(p_payload->'items')
 OR (SELECT count(DISTINCT v->>'lead_id') FROM jsonb_array_elements(p_payload->'items') v)<>jsonb_array_length(p_payload->'items') THEN RAISE EXCEPTION 'Unique request and lead per member required'; END IF;
 fingerprint:=encode(sha256(convert_to(p_payload::text,'UTF8')),'hex');job:=p_payload->>'provider_job_id';
 PERFORM pg_advisory_xact_lock(hashtextextended('propstream-external:'||p_id::text,0));
 SELECT * INTO old FROM wholesale_ingest.propstream_external_submissions WHERE id=p_id;
 IF FOUND THEN
  IF old.operator_id<>p_operator OR old.payload_hash<>fingerprint THEN RAISE EXCEPTION 'External recovery reference conflict'; END IF;
  RETURN old.result||jsonb_build_object('replayed',true,'dispatch',false);
 END IF;
 FOR item IN SELECT v FROM jsonb_array_elements(p_payload->'items') v ORDER BY v->>'lead_id' LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR (item-ARRAY['request_id','lead_id','input_hash'])<>'{}'::jsonb
  OR coalesce(item->>'input_hash','') !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Exact reserved input required'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('trace-lead:'||(item->>'lead_id'),0));
  SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=(item->>'request_id')::uuid FOR UPDATE;
  IF saved.id IS NULL OR saved.lead_id IS DISTINCT FROM (item->>'lead_id')::uuid OR saved.provider<>'propstream'
  OR saved.input_hash IS DISTINCT FROM item->>'input_hash' OR saved.state NOT IN ('reserved','submitted','unknown')
  OR (saved.provider_job_id IS NOT NULL AND saved.provider_job_id<>job)
  OR NOT EXISTS(SELECT 1 FROM wholesale_ingest.propstream_handoffs WHERE request_id=saved.id AND operator_id=p_operator)
  THEN RAISE EXCEPTION 'Matching unresolved PropStream reservation required'; END IF;
  -- Do not pretend a dispatch happened here or recheck eligibility to release an
  -- already external job. Its original hold must survive stale evidence/midnight.
  UPDATE wholesale_ingest.skip_trace_requests SET state='unknown',provider_job_id=job WHERE id=saved.id RETURNING * INTO saved;
  results:=results||jsonb_build_array(jsonb_build_object('request_id',saved.id,'lead_id',saved.lead_id,'state',saved.state,'reserved_cents',saved.reserved_cents));
 END LOOP;
 result:=jsonb_build_object('recovery_id',p_id,'provider_job_id',job,'count',jsonb_array_length(p_payload->'items'),'results',results,
 'dispatch',false,'outreach_authorized',false,'replayed',false);
 INSERT INTO wholesale_ingest.propstream_external_submissions(id,operator_id,payload_hash,payload,result) VALUES(p_id,p_operator,fingerprint,p_payload,result);
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.recover_propstream_external_submission(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.recover_propstream_external_submission(uuid,uuid,jsonb) TO service_role;
COMMIT;
