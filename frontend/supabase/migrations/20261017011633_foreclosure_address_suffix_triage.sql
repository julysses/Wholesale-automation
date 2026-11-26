-- Accept processor 1.2 terminal-suffix triage without rewriting legacy evidence.
-- No evidence backfill, eligibility grant, role change or outbound action.
CREATE OR REPLACE FUNCTION public.save_foreclosure_batch(p_operator uuid,p_batch uuid,p_source text,p_receipt jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE src wholesale_ingest.sources; old wholesale_ingest.foreclosure_batches; n jsonb; c wholesale_ingest.foreclosure_captures;
 stamp timestamptz; day date; summary jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND role='admin' AND status='approved') THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
 SELECT * INTO STRICT src FROM wholesale_ingest.sources WHERE source_key=p_source AND county='Collin' AND list_type='pre_foreclosure';
 IF p_batch IS NULL OR jsonb_typeof(p_receipt) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(p_receipt))<>10
  OR NOT(p_receipt ?& ARRAY['processor','day','processed_at','dataset_url','ownership_snapshot_sha256','report_sha256','verification_granted','dispatch_authorized','outreach_authorized','notices'])
  OR coalesce(p_receipt->>'processor','') NOT IN ('foreclosure-batch/1.0','foreclosure-batch/1.1','foreclosure-batch/1.2')
  OR p_receipt->>'dataset_url' IS DISTINCT FROM 'https://data.texas.gov/d/ahis-pci3'
  OR p_receipt->'verification_granted' IS DISTINCT FROM 'false'::jsonb OR p_receipt->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb
  OR p_receipt->'outreach_authorized' IS DISTINCT FROM 'false'::jsonb
  OR coalesce(p_receipt->>'ownership_snapshot_sha256','') !~ '^[a-f0-9]{64}$'
  OR coalesce(p_receipt->>'report_sha256','') !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Invalid bulk receipt'; END IF;
 stamp:=(p_receipt->>'processed_at')::timestamptz; day:=(p_receipt->>'day')::date;
 IF stamp IS NULL OR NOT isfinite(stamp) OR stamp<'2000-01-01' OR stamp>now()+interval '5 minutes'
  OR day IS NULL OR NOT isfinite(day) OR day>current_date OR day<date '2000-01-01'
  OR jsonb_typeof(p_receipt->'notices') IS DISTINCT FROM 'array' OR jsonb_array_length(p_receipt->'notices') NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid bulk timestamp or size'; END IF;
 IF (SELECT count(DISTINCT value->>'document_id') FROM jsonb_array_elements(p_receipt->'notices'))<>jsonb_array_length(p_receipt->'notices') THEN RAISE EXCEPTION 'Duplicate batch documents'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_batch::text,0));
 SELECT * INTO old FROM wholesale_ingest.foreclosure_batches WHERE id=p_batch;
 IF FOUND THEN
  IF old.source_id<>src.id OR old.operator_id<>p_operator OR old.receipt<>p_receipt THEN RAISE EXCEPTION 'Bulk receipt conflict'; END IF;
  RETURN jsonb_build_object('batch_id',p_batch,'summary',old.summary,'verification_granted',false,'dispatch_authorized',false);
 END IF;
 FOR n IN SELECT value FROM jsonb_array_elements(p_receipt->'notices') LOOP
  IF jsonb_typeof(n) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(n))<>10
   OR NOT(n ?& ARRAY['document_id','html_sha256','text_sha256s','parcel_id','appraisal_situs_matched','notice_situs_supported','trustee_case','auction_date','future_sale','holds'])
   OR coalesce(n->>'document_id','') !~ '^[0-9]{1,30}$' OR coalesce(n->>'html_sha256','') !~ '^[a-f0-9]{64}$'
   OR jsonb_typeof(n->'appraisal_situs_matched') IS DISTINCT FROM 'boolean' OR jsonb_typeof(n->'notice_situs_supported') IS DISTINCT FROM 'boolean'
   OR jsonb_typeof(n->'future_sale') IS DISTINCT FROM 'boolean' OR jsonb_typeof(n->'holds') IS DISTINCT FROM 'array'
   OR jsonb_array_length(n->'holds')>10 OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(n->'holds') h WHERE h !~ '^[a-z_]{1,60}$')
   OR (n->>'parcel_id' IS NOT NULL AND n->>'parcel_id' !~ '^[1-9][0-9]{0,19}$')
   OR ((n->>'appraisal_situs_matched')::boolean AND n->>'parcel_id' IS NULL)
   OR (n->>'trustee_case' IS NOT NULL AND (
    jsonb_typeof(n->'trustee_case') IS DISTINCT FROM 'string' OR NOT (
      n->>'trustee_case' ~ '^[0-9]{4}-[0-9]{3,10}-[A-Z]{2}$'
      OR (p_receipt->>'processor' IN ('foreclosure-batch/1.1','foreclosure-batch/1.2') AND n->>'trustee_case' ~ '^(PLG:[0-9]{2}-[0-9]{6}-[0-9]{1,3}|FIRM:[0-9]{2}-[0-9]{6}|TS:[0-9]{2}-[0-9]{5})$')
    )))
   OR ((n->>'future_sale')::boolean AND ((n->>'auction_date')::date IS NULL OR (n->>'auction_date')::date<=day)) THEN RAISE EXCEPTION 'Invalid batch notice'; END IF;
  SELECT * INTO c FROM wholesale_ingest.foreclosure_captures WHERE source_id=src.id AND source_record_id=n->>'document_id' AND html_sha256=n->>'html_sha256';
  IF NOT FOUND OR jsonb_array_length(c.pages)<>c.expected_pages OR stamp<c.captured_at
   OR jsonb_typeof(n->'text_sha256s') IS DISTINCT FROM 'array' OR jsonb_array_length(n->'text_sha256s')<>c.expected_pages THEN RAISE EXCEPTION 'Batch must match complete county evidence'; END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(n->'text_sha256s') WITH ORDINALITY h(digest,page)
   WHERE NOT EXISTS(SELECT 1 FROM wholesale_ingest.foreclosure_extractions e WHERE e.source_id=src.id AND e.source_record_id=c.source_record_id AND e.html_sha256=c.html_sha256
    AND e.page=h.page AND e.text_sha256=h.digest AND e.extracted_at<=stamp)) THEN RAISE EXCEPTION 'Batch must match extracted county evidence'; END IF;
 END LOOP;
 SELECT jsonb_build_object('county',src.county,'documents',count(*),
  'appraisal_situs_matched',count(*) FILTER(WHERE (value->>'appraisal_situs_matched')::boolean),
  'notice_situs_supported',count(*) FILTER(WHERE (value->>'notice_situs_supported')::boolean),
  'property_groups',count(DISTINCT CASE WHEN (value->>'appraisal_situs_matched')::boolean THEN 'parcel:'||(value->>'parcel_id') ELSE 'notice:'||(value->>'document_id') END),
  'future_sale_documents',count(*) FILTER(WHERE (value->>'future_sale')::boolean),
  'exception_documents',count(*) FILTER(WHERE jsonb_array_length(value->'holds')>0),
  'evidence_review_candidates',count(*) FILTER(WHERE jsonb_array_length(value->'holds')=0),
  'trace_eligible',0) INTO summary FROM jsonb_array_elements(p_receipt->'notices');
 INSERT INTO wholesale_ingest.foreclosure_batches VALUES(p_batch,src.id,p_receipt,summary,stamp,p_operator,now());
 RETURN jsonb_build_object('batch_id',p_batch,'summary',summary,'verification_granted',false,'dispatch_authorized',false);
END; $$;
