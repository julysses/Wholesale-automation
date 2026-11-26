BEGIN;
CREATE TABLE wholesale_ingest.foreclosure_appraisal_batches (
 id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES wholesale_ingest.sources,
 run_id uuid NOT NULL, batch_index integer NOT NULL,
 receipt jsonb NOT NULL, summary jsonb NOT NULL, processed_at timestamptz NOT NULL,
 operator_id uuid NOT NULL REFERENCES public.profiles, received_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(run_id,batch_index) REFERENCES wholesale_ingest.raw_payloads ON DELETE CASCADE
);
CREATE INDEX foreclosure_appraisal_latest ON wholesale_ingest.foreclosure_appraisal_batches(source_id,processed_at DESC,received_at DESC);
ALTER TABLE wholesale_ingest.foreclosure_appraisal_batches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.foreclosure_appraisal_batches FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON wholesale_ingest.foreclosure_appraisal_batches TO service_role;

CREATE FUNCTION public.save_foreclosure_appraisal_batch(p_operator uuid,p_batch uuid,p_receipt jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE old wholesale_ingest.foreclosure_appraisal_batches; src uuid; run uuid; idx integer;
 stamp timestamptz; asof date; item jsonb; summary jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 IF p_batch IS NULL OR jsonb_typeof(p_receipt) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(p_receipt))<>12
  OR NOT(p_receipt ?& ARRAY['processor','run_id','batch_index','records_sha256','archive_sha256','report_sha256','source_as_of','processed_at','items','verification_granted','dispatch_authorized','outreach_authorized'])
  OR p_receipt->>'processor' IS DISTINCT FROM 'dallas-appraisal-batch/1.0'
  OR p_receipt->'verification_granted' IS DISTINCT FROM 'false'::jsonb OR p_receipt->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb
  OR p_receipt->'outreach_authorized' IS DISTINCT FROM 'false'::jsonb
  OR coalesce(p_receipt->>'records_sha256','') !~ '^[a-f0-9]{64}$' OR coalesce(p_receipt->>'archive_sha256','') !~ '^[a-f0-9]{64}$'
  OR coalesce(p_receipt->>'report_sha256','') !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_receipt->'batch_index') IS DISTINCT FROM 'number'
  OR coalesce(p_receipt->>'batch_index','') !~ '^[0-9]+$' THEN RAISE EXCEPTION 'Invalid appraisal receipt'; END IF;
 run:=(p_receipt->>'run_id')::uuid; idx:=(p_receipt->>'batch_index')::integer; stamp:=(p_receipt->>'processed_at')::timestamptz; asof:=(p_receipt->>'source_as_of')::date;
 IF stamp IS NULL OR NOT isfinite(stamp) OR stamp<'2000-01-01' OR stamp>now()+interval '5 minutes' OR asof IS NULL OR NOT isfinite(asof)
  OR asof>(stamp AT TIME ZONE 'UTC')::date OR asof<(stamp AT TIME ZONE 'UTC')::date-1
  OR jsonb_typeof(p_receipt->'items') IS DISTINCT FROM 'array' OR jsonb_array_length(p_receipt->'items') NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid appraisal timestamp or size'; END IF;
 SELECT r.source_id INTO src FROM wholesale_ingest.ingest_runs r JOIN wholesale_ingest.sources s ON s.id=r.source_id
 JOIN wholesale_ingest.raw_payloads p ON p.run_id=r.id AND p.batch_index=idx
 WHERE r.id=run AND s.source_key='tx-dallas-pre_foreclosure' AND p.records_hash=p_receipt->>'records_sha256' AND p.records_in=jsonb_array_length(p_receipt->'items');
 IF src IS NULL OR (SELECT count(*) FROM wholesale_ingest.records WHERE run_id=run AND batch_index=idx)<>jsonb_array_length(p_receipt->'items') THEN RAISE EXCEPTION 'Appraisal batch must match saved Dallas inventory'; END IF;
 IF (SELECT count(DISTINCT value->>'document_id') FROM jsonb_array_elements(p_receipt->'items'))<>jsonb_array_length(p_receipt->'items') THEN RAISE EXCEPTION 'Duplicate appraisal documents'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_receipt->'items') LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(item))<>3 OR NOT(item ?& ARRAY['document_id','match_count','held'])
   OR coalesce(item->>'document_id','') !~ '^[0-9]{1,30}$' OR jsonb_typeof(item->'match_count') IS DISTINCT FROM 'number'
   OR coalesce(item->>'match_count','') !~ '^[0-9]+$' OR (item->>'match_count')::integer NOT BETWEEN 0 AND 100
   OR jsonb_typeof(item->'held') IS DISTINCT FROM 'boolean'
   OR ((item->>'match_count')::integer<>1 AND item->'held' IS DISTINCT FROM 'true'::jsonb)
   OR NOT EXISTS(SELECT 1 FROM wholesale_ingest.records WHERE run_id=run AND batch_index=idx AND source_record_id=item->>'document_id') THEN RAISE EXCEPTION 'Invalid appraisal document'; END IF;
 END LOOP;
 PERFORM pg_advisory_xact_lock(hashtextextended('appraisal-batch:'||p_batch::text,0));
 SELECT * INTO old FROM wholesale_ingest.foreclosure_appraisal_batches WHERE id=p_batch;
 IF FOUND THEN
  IF old.operator_id<>p_operator OR old.receipt<>p_receipt THEN RAISE EXCEPTION 'Appraisal receipt conflict'; END IF;
  RETURN old.summary||jsonb_build_object('batch_id',p_batch,'verification_granted',false);
 END IF;
 SELECT jsonb_build_object('county','Dallas','documents',count(*),'unique_situs_matches',count(*) FILTER(WHERE (value->>'match_count')::int=1),
  'exception_documents',count(*) FILTER(WHERE (value->>'held')::boolean),'trace_eligible',0) INTO summary FROM jsonb_array_elements(p_receipt->'items');
 INSERT INTO wholesale_ingest.foreclosure_appraisal_batches VALUES(p_batch,src,run,idx,p_receipt,summary,stamp,p_operator,now());
 RETURN summary||jsonb_build_object('batch_id',p_batch,'verification_granted',false);
END; $$;

CREATE FUNCTION public.foreclosure_appraisal_status(p_operator uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT coalesce(jsonb_agg(item ORDER BY item->'summary'->>'county'),'[]'::jsonb) INTO result FROM (
  SELECT DISTINCT ON(source_id) jsonb_build_object('batch_id',id,'summary',summary,'source_as_of',receipt->>'source_as_of','processed_at',processed_at) item
  FROM wholesale_ingest.foreclosure_appraisal_batches ORDER BY source_id,processed_at DESC,received_at DESC,id
 ) q;
 RETURN result;
END; $$;
REVOKE ALL ON FUNCTION public.save_foreclosure_appraisal_batch(uuid,uuid,jsonb),public.foreclosure_appraisal_status(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_foreclosure_appraisal_batch(uuid,uuid,jsonb),public.foreclosure_appraisal_status(uuid) TO service_role;
DO $$ DECLARE definition text; BEGIN
 definition:=pg_get_functiondef('public.foreclosure_capture_status(uuid)'::regprocedure);
 IF position('RETURN result ||' IN definition)=0 OR position('appraisal_batches' IN definition)>0 THEN RAISE EXCEPTION 'Unexpected bulk capture status definition'; END IF;
 EXECUTE replace(definition,'RETURN result ||', 'RETURN result || jsonb_build_object(''appraisal_batches'',public.foreclosure_appraisal_status(p_operator)) ||');
END; $$;
COMMIT;
